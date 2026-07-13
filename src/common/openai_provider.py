import json
import httpx
from typing import List, Any, AsyncGenerator
from src.common.config import settings
from src.common.providers import BaseProvider, ChatMessage

class OpenAIProvider(BaseProvider):
    """
    Concrete adapter for the OpenAI cloud provider.
    Implements the BaseProvider contract by consuming the API asynchronously.
    """
    def __init__(self, model_name: str):
        self.model_name = model_name
        self.api_url = "https://api.openai.com/v1/chat/completions"
        
        # Inject the API Key from our secure configuration Singleton
        self.headers = {
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }

    async def generate(self, messages: List[ChatMessage], temperature: float = 0.7) -> str:
        """
        Sends an asynchronous request to OpenAI and extracts the response text.
        """
        # Map message objects to the dictionary format required by the API
        formatted_messages = [
            {"role": msg.role, "content": msg.content} for msg in messages
        ]
        
        payload = {
            "model": self.model_name,
            "messages": formatted_messages,
            "temperature": temperature
        }

        try:
            # Initialize a non-blocking async HTTP client with a 30-second timeout
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.api_url, 
                    headers=self.headers, 
                    json=payload
                )
                
                # If OpenAI responds with an error code (e.g., 401 or 429), raise an exception
                if response.status_code != 200:
                    raise RuntimeError(
                        f"OpenAI API Error [{response.status_code}]: {response.text}"
                    )
                
                # Parse the standard JSON response
                data = response.json()
                return data["choices"][0]["message"]["content"]
                
        except httpx.RequestError as e:
            # Capture physical network failures (internet drop, DNS issues, etc.)
            raise RuntimeError(f"Failed to connect to OpenAI cloud endpoints: {str(e)}")

    async def generate_stream(self, messages: List[ChatMessage], **kwargs: Any) -> AsyncGenerator[str, None]:
        """
        Asynchronously streams the generated tokens from the OpenAI endpoint
        by parsing Server-Sent Events (SSE) data chunks line-by-line.
        """
        formatted_messages = [
            {"role": msg.role, "content": msg.content} for msg in messages
        ]
        
        payload = {
            "model": self.model_name,
            "messages": formatted_messages,
            "stream": True,  # Forcing cloud event-stream generation
            **kwargs
        }

        # Initialize stream pipeline using httpx connection pooling
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                async with client.stream("POST", self.api_url, headers=self.headers, json=payload) as response:
                    if response.status_code != 200:
                        # Stream response chunks require reading full byte body under error states
                        error_text = await response.aread()
                        raise RuntimeError(
                            f"OpenAI API Stream Error [{response.status_code}]: {error_text.decode()}"
                        )
                    
                    # Consume the persistent stream buffer
                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line:
                            continue
                        
                        # SSE payload compliance: verify and strip the protocol prefix
                        if line.startswith("data: "):
                            data_content = line[6:].strip()
                            
                            # End-of-stream delimiter sent by OpenAI
                            if data_content == "[DONE]":
                                break
                            
                            try:
                                chunk_data = json.loads(data_content)
                                choices = chunk_data.get("choices", [])
                                if choices:
                                    # Streams inject partial words inside the 'delta' dictionary
                                    token = choices[0].get("delta", {}).get("content", "")
                                    if token:
                                        yield token
                            except json.JSONDecodeError:
                                # Shield connection against raw split byte malformations
                                continue
                                
            except httpx.RequestError as e:
                raise RuntimeError(f"Failed to connect to OpenAI cloud endpoints during stream: {str(e)}")