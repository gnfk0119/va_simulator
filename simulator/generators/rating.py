import json
from simulator.llm.base import LLMClient
from simulator.schemas import Rating
from simulator.utils.prompt_loader import PromptLoader
from simulator.utils.json_utils import safe_load_json


class RatingGenerator:
    def __init__(self, llm: LLMClient, prompts_dir: str = "prompts") -> None:
        self._llm = llm
        self._loader = PromptLoader(prompts_dir)

    def self_rate(self, dialogue_turn: dict, hidden_context: str, public_state: dict, memory_json: str) -> Rating:
        prompt = self._loader.load("self_rating.txt")
        user = prompt.format(
            dialogue_turn_json=json.dumps(dialogue_turn, ensure_ascii=False, indent=2),
            hidden_context=hidden_context,
            public_state_json=json.dumps(public_state, ensure_ascii=False, indent=2),
            memory_json=memory_json,
        )
        resp = self._llm.generate("You rate your interaction.", user)
        data = safe_load_json(resp.text)
        if not data:
            return Rating(score=4, reason="응답이 무난함")
        return Rating(score=int(data.get("score", 4)), reason=str(data.get("reason", "")))

    def third_party_rate(self, dialogue_turn: dict) -> Rating:
        prompt = self._loader.load("third_party_rating.txt")
        user = prompt.format(
            dialogue_turn_json=json.dumps(dialogue_turn, ensure_ascii=False, indent=2),
        )
        resp = self._llm.generate("You are a third-party rater.", user)
        data = safe_load_json(resp.text)
        if not data:
            return Rating(score=4, reason="대화만으로 볼 때 적절함")
        return Rating(score=int(data.get("score", 4)), reason=str(data.get("reason", "")))
