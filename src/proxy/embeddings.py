import httpx
from typing import List
from src.common.config import settings
from src.utils.logger import logger

DEFAULT_EMBED_MODEL = "nomic-embed-text"

class EmbeddingsEngine:
    @staticmethod
    async def get_embedding(text: str, model: str = DEFAULT_EMBED_MODEL) -> List[float]:
        """
        Send a plain text to the Ollama's endpoint and extract his vector from embeddings
        asynchronously and non-blocking.
        """
        embed_url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/embeddings"
        payload = {
            "model": model,
            "prompt": text
        }
        
        try:
            async with httpx.AsyncClient(timeout=10.0, trust_env = False) as client:
                response = await client.post(embed_url, json=payload)
                
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
            logger.error("Connection failed to Ollama daemon", extra={"extra_data": {"error": str(e)}})
            raise RuntimeError(f"Embeddings engine connection failure: {str(e)}")