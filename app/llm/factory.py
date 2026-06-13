from app.config import settings
from app.llm.base import LLMProvider
from app.llm.providers.ollama import OllamaProvider


def get_provider(provider_name: str | None = None) -> LLMProvider:
    name = (provider_name or settings.default_provider).lower()

    if name == "ollama":
        return OllamaProvider(
            model_name=settings.ollama_model,
            base_url=settings.ollama_base_url,
        )

    raise ValueError(f"Unsupported provider: {name}")
