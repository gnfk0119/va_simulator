from dataclasses import dataclass
from typing import Optional


@dataclass
class LLMResponse:
    text: str


class LLMClient:
    def generate(self, system: str, user: str, temperature: Optional[float] = None) -> LLMResponse:
        raise NotImplementedError
