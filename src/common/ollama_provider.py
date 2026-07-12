from typing import List, Any
import httpx
from src.common.providers import BaseProvider, ChatMessage

class OllamaProvider(BaseProvider):
    """
    Concrete implementation of BaseProvider for interacting with a local Ollama instance.
    """
    
    def __init__(self, base_url: str = "http://localhost:11434", model_name: str = "llama3"):
        """
        Initializes the Ollama adapter.
        
        :param base_url: The network address where Ollama is listening.
        :param model_name: The specific local model to target (e.g., llama3, mistral, phi3).
        """
        self.base_url = f"{base_url.rstrip('/')}/api/chat"
        self.model_name = model_name

    async def generate(self, messages: List[ChatMessage], **kwargs: Any) -> str:
        """
        Transforms standardized messages into Ollama format, triggers an async HTTP 
        request to the local daemon, and extracts the text response.
        """
        # Step 1: Transform Pydantic models into a raw dictionary payload expected by Ollama
        formatted_messages = [
            {"role": msg.role, "content": msg.content} for msg in messages
        ]
        
        payload = {
            "model": self.model_name,
            "messages": formatted_messages,
            "stream": False,  # We will handle streaming architecture in later iterations
            **kwargs
        }
        
        # Step 2: Fire an non-blocking HTTP POST request using httpx
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    self.base_url,
                    json=payload,
                    timeout=30.0  # Safe timeout boundary for local inference
                )
                response.raise_for_status()
                
                # Step 3: Parse and extract the response string safely
                response_data = response.json()
                return response_data["message"]["content"]
                
            except httpx.HTTPStatusError as e:
                # In a real infrastructure tool, we catch and log vendor-specific errors cleanly
                raise RuntimeError(f"Ollama upstream server returned error status: {e.response.status_code}")
            except httpx.RequestError as e:
                raise RuntimeError(f"Failed to establish connection with local Ollama daemon: {e}")