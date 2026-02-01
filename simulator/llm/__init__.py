from simulator.llm.base import LLMClient, LLMResponse
from simulator.llm.mock import MockLLM
from simulator.llm.openai_sync import OpenAISyncClient


def create_llm(provider: str, seed: int = 42, model: str = "gpt-4o") -> LLMClient:
    if provider == "mock":
        return MockLLM(seed=seed)
    if provider == "openai":
        return OpenAISyncClient(model=model)
    raise ValueError(f"Unsupported provider: {provider}")
