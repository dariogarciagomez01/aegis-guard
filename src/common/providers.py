from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import List, Any

class ChatMessage(BaseModel):
    """
    Standardized schema for chat messages flowing through Aegis Guard.
    Mimics the OpenAI message structure (role and content).
    """
    role: str
    content: str

class LLMProvider(ABC):
    """
    Abstract Base Class acting as the strict contract for all AI providers
    integrated into the Aegis Guard ecosystem.
    """
    
    @abstractmethod
    async def generate(self, messages: List[ChatMessage], **kwargs: Any) -> str:
        """
        Asynchronously forwards the standardized message history to the upstream 
        LLM provider and returns the raw string response.
        
        :param messages: A list of ChatMessage objects representing the conversation history.
        :param kwargs: Additional model parameters (temperature, max_tokens, etc.).
        :return: The generated text response from the model.
        """
        pass