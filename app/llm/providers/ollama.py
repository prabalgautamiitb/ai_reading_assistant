from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

from app.llm.base import LLMProvider
from app.prompts import SYSTEM_PROMPT, build_user_prompt
from app.schemas import ExplainMode


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self, model_name: str, base_url: str) -> None:
        self.model_name = model_name
        self._chat = ChatOllama(
            model=model_name,
            base_url=base_url,
            temperature=0.2,
        )

    async def explain(self, text: str, mode: ExplainMode) -> str:
        prompt = build_user_prompt(text=text, mode=mode)
        response = await self._chat.ainvoke(
            [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ]
        )
        return str(response.content).strip()
