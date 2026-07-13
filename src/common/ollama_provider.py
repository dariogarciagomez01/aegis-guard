import json
from typing import List, Any, AsyncGenerator
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

    async def generate_stream(self, messages: List[ChatMessage], **kwargs: Any) -> AsyncGenerator[str, None]:
        """
        Transforms standardized messages into Ollama format, opens a persistent 
        asynchronous network connection, and yields text tokens sequentially as they arrive.
        """
        # Step 1: Format messages and enforce the streaming flag in the payload
        formatted_messages = [
            {"role": msg.role, "content": msg.content} for msg in messages
        ]
        
        payload = {
            "model": self.model_name,
            "messages": formatted_messages,
            "stream": True,  # Activating real-time token yielding
            **kwargs
        }
        
        # Step 2: Establish a persistent connection context utilizing client.stream
        async with httpx.AsyncClient() as client:
            try:
                async with client.stream("POST", self.base_url, json=payload, timeout=30.0) as response:
                    response.raise_for_status()
                    
                    # Step 3: Consume and decode the byte stream line-by-line without blocking
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        
                        try:
                            # Ollama streams lines of independent valid JSON structures
                            chunk_data = json.loads(line)
                            token = chunk_data.get("message", {}).get("content", "")
                            if token:
                                yield token
                        except json.JSONDecodeError:
                            # Protect chunk stability against malformed or truncated packet splits
                            continue
                            
            except httpx.HTTPStatusError as e:
                raise RuntimeError(f"Ollama upstream server returned error status: {e.response.status_code}")
            except httpx.RequestError as e:
                raise RuntimeError(f"Failed to establish connection with local Ollama daemon: {e}")