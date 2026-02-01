import json
from typing import List

from simulator.llm.base import LLMClient
from simulator.schemas import DialogueTurn, Persona, Environment
from simulator.utils.prompt_loader import PromptLoader


class DialogueGenerator:
    def __init__(self, llm: LLMClient, prompts_dir: str = "prompts") -> None:
        self._llm = llm
        self._loader = PromptLoader(prompts_dir)

    def generate_avatar_command(self, persona: Persona, environment: Environment, public_state: dict, hidden_context: str, memory_json: str) -> str:
        prompt = self._loader.load("avatar_command.txt")
        user = prompt.format(
            persona_json=json.dumps(persona.data, ensure_ascii=False, indent=2),
            public_state_json=json.dumps(public_state, ensure_ascii=False, indent=2),
            hidden_context=hidden_context,
            memory_json=memory_json,
            environment_json=json.dumps(environment.raw_profile, ensure_ascii=False, indent=2),
        )
        resp = self._llm.generate("You generate avatar commands.", user)
        return resp.text.strip()

    def generate_va_response(self, environment: Environment, public_state: dict, dialogue_history: List[DialogueTurn]) -> str:
        prompt = self._loader.load("va_response.txt")
        user = prompt.format(
            public_state_json=json.dumps(public_state, ensure_ascii=False, indent=2),
            dialogue_json=json.dumps([d.__dict__ for d in dialogue_history], ensure_ascii=False, indent=2),
            environment_json=json.dumps(environment.raw_profile, ensure_ascii=False, indent=2),
        )
        resp = self._llm.generate("You are a voice assistant.", user)
        return resp.text.strip()

    def run(self, persona: Persona, environment: Environment, public_state: dict, hidden_context: str, memory_json: str, max_turns: int) -> List[DialogueTurn]:
        turns: List[DialogueTurn] = []
        turn_id = 1

        # Avatar starts
        avatar_cmd = self.generate_avatar_command(persona, environment, public_state, hidden_context, memory_json)
        turns.append(DialogueTurn(turn_id=turn_id, speaker="Avatar", text=avatar_cmd))
        turn_id += 1

        # VA response
        va_resp = self.generate_va_response(environment, public_state, turns)
        turns.append(DialogueTurn(turn_id=turn_id, speaker="VA", text=va_resp))
        turn_id += 1

        # Optional additional turns
        while turn_id <= max_turns:
            avatar_cmd = self.generate_avatar_command(persona, environment, public_state, hidden_context, memory_json)
            turns.append(DialogueTurn(turn_id=turn_id, speaker="Avatar", text=avatar_cmd))
            turn_id += 1
            if turn_id > max_turns:
                break
            va_resp = self.generate_va_response(environment, public_state, turns)
            turns.append(DialogueTurn(turn_id=turn_id, speaker="VA", text=va_resp))
            turn_id += 1

        return turns
