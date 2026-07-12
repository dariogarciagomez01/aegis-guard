import httpx
from typing import List
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