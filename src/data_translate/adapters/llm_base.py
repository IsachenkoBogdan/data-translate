from typing import Protocol

from data_translate.adapters.llm_response import LLMResponse


class LLMChatAdapter(Protocol):
    async def chat(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse: ...

    async def close(self) -> None: ...
