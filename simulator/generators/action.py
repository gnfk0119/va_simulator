import json
from typing import List

from simulator.llm.base import LLMClient
from simulator.schemas import Action, Persona, Environment
from simulator.utils.prompt_loader import PromptLoader
from simulator.utils.json_utils import safe_load_json
from simulator.utils.time_utils import add_minutes


class ActionGenerator:
    def __init__(self, llm: LLMClient, prompts_dir: str = "prompts") -> None:
        self._llm = llm
        self._loader = PromptLoader(prompts_dir)

    def generate(self, persona: Persona, environment: Environment, schedule_day: List[dict], public_state: dict, memory_json: str, current_time: str, time_step: int) -> Action:
        prompt = self._loader.load("action.txt")
        user = prompt.format(
            persona_json=json.dumps(persona.data, ensure_ascii=False, indent=2),
            schedule_day_json=json.dumps(schedule_day, ensure_ascii=False, indent=2),
            public_state_json=json.dumps(public_state, ensure_ascii=False, indent=2),
            memory_json=memory_json,
            environment_json=json.dumps(environment.raw_profile, ensure_ascii=False, indent=2),
        )
        resp = self._llm.generate("You generate visible actions.", user)
        data = safe_load_json(resp.text)
        if not data:
            if schedule_day:
                item = schedule_day[0]
                return Action(
                    time=item.get("start", current_time),
                    location=item.get("location", ""),
                    visible_action=item.get("activity", "일상 활동"),
                    device_targets=item.get("device_targets", []),
                    notes=""
                )
            return Action(
                time=add_minutes(current_time, time_step),
                location=public_state.get("location", ""),
                visible_action="일상 활동",
                device_targets=[],
                notes=""
            )
        return Action(
            time=data.get("time", current_time),
            location=data.get("location", ""),
            visible_action=data.get("visible_action", ""),
            device_targets=list(data.get("device_targets", [])),
            notes=data.get("notes", "")
        )
