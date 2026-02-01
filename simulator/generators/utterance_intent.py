import json

from simulator.llm.base import LLMClient
from simulator.schemas import UtteranceIntent, Action
from simulator.utils.prompt_loader import PromptLoader
from simulator.utils.json_utils import safe_load_json


class UtteranceIntentGenerator:
    def __init__(self, llm: LLMClient, prompts_dir: str = "prompts") -> None:
        self._llm = llm
        self._loader = PromptLoader(prompts_dir)

    def generate(self, action: Action, hidden_context: str, memory_json: str, threshold: float) -> UtteranceIntent:
        prompt = self._loader.load("utterance_intent.txt")
        user = prompt.format(
            action_json=json.dumps(action.__dict__, ensure_ascii=False, indent=2),
            hidden_context=hidden_context,
            memory_json=memory_json,
            threshold=threshold,
        )
        resp = self._llm.generate("You decide utterance intent.", user)
        data = safe_load_json(resp.text)
        if not data:
            return UtteranceIntent(score=0.0, threshold=threshold, should_speak=False, rationale="")
        return UtteranceIntent(
            score=float(data.get("score", 0.0)),
            threshold=float(data.get("threshold", threshold)),
            should_speak=bool(data.get("should_speak", False)),
            rationale=str(data.get("rationale", "")),
        )
