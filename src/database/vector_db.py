import os
import lancedb
import time
import pyarrow as pa
from typing import List, Optional

# Local Storage path for LanceDB
DB_PATH = os.path.join("src", "database", "vector_store")
TABLE_NAME = "semantic_cache"

# Local reference for the database and the table
_db_client = None
_cache_table = None

def get_vector_db():
    """
    Initialize the LanceDB client using a Singleton pattern to avoid
    opening duplicated embeddings to the file system.
    """
    global _db_client
    if _db_client is None:
        # Ensure that the directory exists
        os.makedirs(DB_PATH, exist_ok=True)
        _db_client = lancedb.connect(DB_PATH)
    return _db_client

def init_vector_db(vector_dim: int = 768):
    """
    Initialize the vectorial database and creates the table if doesn't exist.
    It uses an explicit schema with PyArrow for a strict type

    Note: The default Llama 3 vector_dim is 4096
    If OpenAI text-embedding-3-small being used, change to 1536.
    """
    global _cache_table
    db = get_vector_db()
    
    # We define the strict schema using PyArrow to gurantee good performance
    schema = pa.schema([
        # Prompt vector (It has to coincide the dimensions)
        pa.field("vector", pa.list_(pa.float32(), list_size=vector_dim)),
        pa.field("prompt_text", pa.string()),
        pa.field("response_text", pa.string()),
        pa.field("model_used", pa.string()),
        pa.field("created_at", pa.float64())
    ])
    
    if TABLE_NAME in db.table_names():
        _cache_table = db.open_table(TABLE_NAME)
        print(f"[VECTOR-DB] Loaded existing semantic cache table: '{TABLE_NAME}'")
    else:
        # Creates the clean table with the defined schema
        _cache_table = db.create_table(TABLE_NAME, schema=schema)
        print(f"[VECTOR-DB] Created new semantic cache table: '{TABLE_NAME}' with dim={vector_dim}")
        
    return _cache_table

def get_cache_table():
    """Obtains the active reference to the cache table"""
    global _cache_table
    if _cache_table is None:
        raise RuntimeError("Vector database has not been initialized. Call init_vector_db() first.")
    return _cache_table


def search_semantic_cache(query_vector: List[float], threshold: float = 0.88) -> Optional[dict]:
    """
    Searches the nearest vector in LanceDB using the cosine similarity.
    Calculates the similarity (1 - distance) and if it surpasses the threshold,
    devolves the cache data. If not, devolves None.
    """
    table = get_cache_table()
    
    # Search for the nearest neighbor (limit 1) using cosine distance
    results = table.search(query_vector).metric("cosine").limit(1).to_list()
    
    if not results:
        return None
        
    match = results[0]
    # In LanceDB with cosine metric: distance = 1 - similarity
    # Therefore: similarity = 1 - distance
    distance = match.get("_distance", 1.0)
    similarity_score = 1.0 - distance
    
    print(f"[VECTOR-DB] Top match similarity score: {similarity_score:.4f} (Threshold: {threshold})")
    
    if similarity_score >= threshold:
        return {
            "prompt_text": match["prompt_text"],
            "response_text": match["response_text"],
            "model_used": match["model_used"],
            "similarity_score": similarity_score
        }
        
    return None

def save_to_cache(vector: List[float], prompt: str, response: str, model: str):
    """
    Inserts a new record into the semantic cache table.
    """
    table = get_cache_table()
    
    record = {
        "vector": vector,
        "prompt_text": prompt,
        "response_text": response,
        "model_used": model,
        "created_at": time.time()
    }
    
    # Insert the record as a list of dictionaries
    table.add([record])
    print(f"[VECTOR-DB] Successfully cached new semantic entry for model: {model}")