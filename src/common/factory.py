from src.common.providers import BaseProvider
from src.common.ollama_provider import OllamaProvider
from src.common.openai_provider import OpenAIProvider
from src.common.config import settings

class ProviderFactory:
    """
    Centralized Factory to dynamically resolve and instantiate AI providers
    based on the requested model name, ensuring loose coupling.
    """
    
    @staticmethod
    def get_provider(model_name: str) -> BaseProvider:
        """
        Evaluates the model string and returns the corresponding concrete adapter
        upcasted to the unified BaseProvider interface.
        
        :param model_name: The target model identifier (e.g., 'gpt-4o', 'llama3')
        :return: An instance of a class implementing BaseProvider
        """
        model_lower = model_name.lower()
        
        # Cloud Routing Architecture
        if model_lower.startswith("gpt-") or "openai" in model_lower:
            return OpenAIProvider(model_name=model_name)
            
        # Local Infrastructure Routing Architecture
        # Defaulting to Ollama for local models (e.g., llama3, mistral, phi3)
        return OllamaProvider(base_url=settings.OLLAMA_BASE_URL, model_name=model_name)