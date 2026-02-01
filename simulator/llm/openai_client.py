import os
from typing import Optional

from dotenv import load_dotenv
from openai import AsyncOpenAI

from simulator.llm.base import LLMClient, LLMResponse


class OpenAIClient(LLMClient):
    def __init__(self, model: str = "gpt-4o", api_key: Optional[str] = None) -> None:
        load_dotenv()
        key = api_key or os.getenv("OPENAI_API_KEY")
        if not key:
            raise ValueError("OPENAI_API_KEY is not set.")
        self._client = AsyncOpenAI(api_key=key)
        self._model = model

    async def generate_async(self, system: str, user: str, temperature: Optional[float] = None) -> LLMResponse:
        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature if temperature is not None else 0.7,
        )
        return LLMResponse(resp.choices[0].message.content.strip())

    def generate(self, system: str, user: str, temperature: Optional[float] = None) -> LLMResponse:
        raise RuntimeError("OpenAIClient requires async usage. Use generate_async in async pipeline.")
