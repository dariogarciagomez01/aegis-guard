from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    Centralized Configuration Management of Aegis Guard.
    Loads and validates automatically the system environment variables
    """

    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OPENAI_API_KEY: str

    model_config = SettingsConfigDict(
        env_file=".env",           
        env_file_encoding="utf-8",
        extra="ignore"
    )

# Singleton pattern
settings = Settings()