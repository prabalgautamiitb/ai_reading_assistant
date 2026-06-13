from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Reading Assistant"
    default_provider: str = "ollama"
    ollama_model: str = "gemma3:latest"
    ollama_base_url: str = "http://localhost:11434"
    host: str = "127.0.0.1"
    port: int = 8000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
