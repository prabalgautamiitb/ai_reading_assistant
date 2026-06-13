from abc import ABC, abstractmethod

from app.schemas import ExplainMode


class LLMProvider(ABC):
    name: str
    model_name: str

    @abstractmethod
    async def explain(self, text: str, mode: ExplainMode) -> str:
        raise NotImplementedError
