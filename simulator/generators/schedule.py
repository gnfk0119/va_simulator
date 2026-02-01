import json
from simulator.llm.base import LLMClient
from simulator.schemas import ScheduleWeek, Persona, Environment
from simulator.utils.prompt_loader import PromptLoader
from simulator.utils.json_utils import safe_load_json


class ScheduleGenerator:
    def __init__(self, llm: LLMClient, prompts_dir: str = "prompts") -> None:
        self._llm = llm
        self._loader = PromptLoader(prompts_dir)

    def generate_week(self, persona: Persona, environment: Environment) -> ScheduleWeek:
        prompt = self._loader.load("schedule_week.txt")
        user = prompt.format(
            persona_json=json.dumps(persona.data, ensure_ascii=False, indent=2),
            environment_json=json.dumps(environment.raw_profile, ensure_ascii=False, indent=2),
        )
        resp = self._llm.generate("You generate weekly schedules.", user)
        data = safe_load_json(resp.text)
        if not data:
            data = {"week": {"Monday": [], "Tuesday": [], "Wednesday": [], "Thursday": [], "Friday": [], "Saturday": [], "Sunday": []}}
        return ScheduleWeek(data=data)
