import json
import random
from typing import Optional

from simulator.llm.base import LLMClient, LLMResponse


class MockLLM(LLMClient):
    def __init__(self, seed: int = 42) -> None:
        self._rng = random.Random(seed)

    def generate(self, system: str, user: str, temperature: Optional[float] = None) -> LLMResponse:
        # Heuristic mock outputs based on simple keywords.
        lowered = user.lower()
        if "persona" in lowered:
            data = {
                "id": f"U{self._rng.randint(1, 999)}",
                "name": "민준",
                "age": 29,
                "gender": "남성",
                "occupation": "회사원",
                "communication_style": "간결하고 정중한 말투",
                "tech_familiarity": "보통",
                "routine_preferences": "규칙적인 생활",
                "preferences": ["커피", "정리정돈"],
                "dislikes": ["소음", "지연"],
                "persona_description": "일상에서 실용성을 중시하는 인물이다."
            }
            return LLMResponse(json.dumps(data, ensure_ascii=False))
        if "weekly schedule" in lowered or "schedule" in lowered:
            data = {
                "week": {
                    "Monday": [
                        {"start": "08:00", "end": "08:20", "location": "kitchen", "activity": "커피 내리기", "device_targets": ["coffee maker"]},
                        {"start": "08:30", "end": "09:00", "location": "bedroom", "activity": "옷 정리", "device_targets": []}
                    ],
                    "Tuesday": [], "Wednesday": [], "Thursday": [], "Friday": [], "Saturday": [], "Sunday": []
                }
            }
            return LLMResponse(json.dumps(data, ensure_ascii=False))
        if "utterance" in lowered and "threshold" in lowered:
            score = round(self._rng.uniform(0.3, 0.9), 2)
            data = {
                "score": score,
                "threshold": 0.6,
                "should_speak": score >= 0.6,
                "rationale": "현재 작업을 위해 도움이 필요하다고 판단함"
            }
            return LLMResponse(json.dumps(data, ensure_ascii=False))
        if "rating" in lowered:
            data = {"score": self._rng.randint(3, 6), "reason": "응답이 적절했음"}
            return LLMResponse(json.dumps(data, ensure_ascii=False))
        if "visible action" in lowered or "action" in lowered:
            data = {
                "time": "08:00",
                "location": "kitchen",
                "visible_action": "커피를 내린다",
                "device_targets": ["coffee maker"],
                "notes": "아침 루틴"
            }
            return LLMResponse(json.dumps(data, ensure_ascii=False))
        if "hidden context" in lowered:
            return LLMResponse("잠을 덜 깬 상태라 빠르게 커피를 마시고 싶다.")
        if "command" in lowered:
            return LLMResponse("커피 머신을 켜줘.")
        if "assistant" in lowered or "response" in lowered:
            return LLMResponse("커피 머신을 켰어요. 이제 추출을 시작할까요?")
        return LLMResponse("알겠습니다.")
