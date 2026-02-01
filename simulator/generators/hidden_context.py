import json
from simulator.llm.base import LLMClient
from simulator.schemas import HiddenContext, Persona, Environment, Action
from simulator.utils.prompt_loader import PromptLoader


class HiddenContextGenerator:
    def __init__(self, llm: LLMClient, prompts_dir: str = "prompts") -> None:
        self._llm = llm
        self._loader = PromptLoader(prompts_dir)

    def generate(self, persona: Persona, environment: Environment, action: Action, memory_json: str) -> HiddenContext:
        prompt = self._loader.load("hidden_context.txt")
        user = prompt.format(
            persona_json=json.dumps(persona.data, ensure_ascii=False, indent=2),
            action_json=json.dumps(action.__dict__, ensure_ascii=False, indent=2),
            memory_json=memory_json,
            environment_json=json.dumps(environment.raw_profile, ensure_ascii=False, indent=2),
        )
        resp = self._llm.generate("You generate hidden context.", user)
        text = resp.text.strip() or ""
        return HiddenContext(text=text)
