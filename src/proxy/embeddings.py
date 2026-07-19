import httpx
from typing import List

OLLAMA_EMBED_URL = "http://127.0.0.1:11434/api/embeddings"
DEFAULT_EMBED_MODEL = "nomic-embed-text"

class EmbeddingsEngine:
    @staticmethod
    async def get_embedding(text: str, model: str = DEFAULT_EMBED_MODEL) -> List[float]:
        """
        Send a plain text to the Ollama's endpoint and extract his vector from embeddings
        asynchronously and non-blocking.
        """
        payload = {
            "model": model,
            "prompt": text
        }
        
        try:
            async with httpx.AsyncClient(timeout=10.0, trust_env = False) as client:
                response = await client.post(OLLAMA_EMBED_URL, json=payload)
                
                if response.status_code != 200:
                    raise RuntimeError(
                        f"Ollama embeddings API returned status {response.status_code}: {response.text}"
                    )
                
                data = response.json()
                embedding = data.get("embedding")
                if not embedding:
                    raise ValueError("Ollama response did not contain 'embedding' vector.")
                
                return embedding
                
        except httpx.RequestError as e:
            print(f"[ERROR-EMBEDDINGS] Connection failed to Ollama daemon: {str(e)}")
            raise RuntimeError(f"Embeddings engine connection failure: {str(e)}")