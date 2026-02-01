import json
from simulator.llm.base import LLMClient
from simulator.schemas import Persona, Environment
from simulator.utils.prompt_loader import PromptLoader
from simulator.utils.json_utils import safe_load_json


class PersonaGenerator:
    def __init__(self, llm: LLMClient, prompts_dir: str = "prompts") -> None:
        self._llm = llm
        self._loader = PromptLoader(prompts_dir)

    def generate(self, environment: Environment) -> Persona:
        prompt = self._loader.load("persona.txt")
        user = prompt.format(environment_json=json.dumps(environment.raw_profile, ensure_ascii=False, indent=2))
        resp = self._llm.generate("You generate personas.", user)
        data = safe_load_json(resp.text)
        if not data:
            data = {
                "id": "U1",
                "name": "지민",
                "age": 30,
                "gender": "여성",
                "occupation": "직장인",
                "communication_style": "차분하고 간결함",
                "tech_familiarity": "보통",
                "routine_preferences": "규칙적인 생활",
                "preferences": ["따뜻한 음료", "정리정돈"],
                "dislikes": ["소음", "지연"],
                "persona_description": "일상에서 실용성을 중시하는 인물이다."
            }
        return Persona(data=data)
