import json
import random
from typing import Dict, List

from simulator.config import Config
from simulator.generators.environment import generate_environment
from simulator.generators.persona import PersonaGenerator
from simulator.generators.schedule import ScheduleGenerator
from simulator.generators.action import ActionGenerator
from simulator.generators.hidden_context import HiddenContextGenerator
from simulator.generators.utterance_intent import UtteranceIntentGenerator
from simulator.generators.dialogue import DialogueGenerator
from simulator.generators.rating import RatingGenerator
from simulator.io.backup import BackupManager
from simulator.io.log_store import LogStore
from simulator.io.excel_export import export_to_excel
from simulator.llm import create_llm
from simulator.memory import MemoryStore
from simulator.state import PublicStateManager
from simulator.utils.time_utils import add_minutes


class SimulationRunner:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._rng = random.Random(config.seed)

    def run(self) -> str:
        cfg = self._config
        llm = create_llm(
            cfg.llm.get("provider", "mock"),
            seed=cfg.seed,
            model=cfg.llm.get("model", "gpt-4o"),
        )

        env = generate_environment(
            base_profile_path=cfg.environment.get("base_profile_path"),
            num_rooms=cfg.environment.get("num_rooms", 4),
            num_devices=cfg.environment.get("num_devices", 10),
            seed=cfg.seed,
        )

        persona_gen = PersonaGenerator(llm)
        schedule_gen = ScheduleGenerator(llm)
        action_gen = ActionGenerator(llm)
        hidden_gen = HiddenContextGenerator(llm)
        intent_gen = UtteranceIntentGenerator(llm)
        dialogue_gen = DialogueGenerator(llm)
        rating_gen = RatingGenerator(llm)

        backup_cfg = cfg.backup
        backup_mgr = BackupManager(
            mode=backup_cfg.get("mode", "every_step"),
            every_n=int(backup_cfg.get("every_n", 1)),
            directory=backup_cfg.get("dir", "data/backup"),
        )

        logs = LogStore()

        for user_index in range(cfg.num_users):
            persona = persona_gen.generate(env)
            schedule_week = schedule_gen.generate_week(persona, env)

            day_name = cfg.day_to_simulate or "Monday"
            schedule_day = schedule_week.get_day(day_name)

            start_time = schedule_day[0].get("start", "08:00") if schedule_day else "08:00"
            available_devices = list(env.device_states.keys())
            public_state_mgr = PublicStateManager(env.device_states.copy(), available_devices, start_time)

            memory = MemoryStore()

            current_time = start_time

            for step in range(1, cfg.interaction_iteration + 1):
                memory_json = memory.to_json()
                public_state = public_state_mgr.to_dict()

                action = action_gen.generate(
                    persona=persona,
                    environment=env,
                    schedule_day=schedule_day,
                    public_state=public_state,
                    memory_json=memory_json,
                    current_time=current_time,
                    time_step=cfg.time_step_minutes,
                )

                public_state_mgr.update(action)
                current_time = action.time or add_minutes(current_time, cfg.time_step_minutes)

                hidden = hidden_gen.generate(persona, env, action, memory_json)
                intent = intent_gen.generate(action, hidden.text, memory_json, cfg.utterance_threshold)

                # Log public/private
                logs.add_public({
                    "user_id": persona.data.get("id", f"U{user_index+1}"),
                    "step": step,
                    **public_state_mgr.to_dict(),
                    "visible_action": action.visible_action,
                })
                logs.add_private({
                    "user_id": persona.data.get("id", f"U{user_index+1}"),
                    "step": step,
                    "hidden_context": hidden.text,
                })

                dialogue_turns = []
                if intent.should_speak:
                    dialogue_turns = dialogue_gen.run(
                        persona=persona,
                        environment=env,
                        public_state=public_state_mgr.to_dict(),
                        hidden_context=hidden.text,
                        memory_json=memory_json,
                        max_turns=cfg.dialogue_max_turns,
                    )

                    for turn in dialogue_turns:
                        logs.add_dialogue({
                            "user_id": persona.data.get("id", f"U{user_index+1}"),
                            "step": step,
                            "turn_id": turn.turn_id,
                            "speaker": turn.speaker,
                            "text": turn.text,
                        })

                        self_rating = rating_gen.self_rate(
                            dialogue_turn=turn.__dict__,
                            hidden_context=hidden.text,
                            public_state=public_state_mgr.to_dict(),
                            memory_json=memory_json,
                        )
                        third_rating = rating_gen.third_party_rate(turn.__dict__)

                        logs.add_self_rating({
                            "user_id": persona.data.get("id", f"U{user_index+1}"),
                            "step": step,
                            "turn_id": turn.turn_id,
                            "score": self_rating.score,
                            "reason": self_rating.reason,
                        })
                        logs.add_third_rating({
                            "user_id": persona.data.get("id", f"U{user_index+1}"),
                            "step": step,
                            "turn_id": turn.turn_id,
                            "score": third_rating.score,
                            "reason": third_rating.reason,
                        })

                # Update memory
                memory.add({
                    "step": step,
                    "action": action.__dict__,
                    "hidden_context": hidden.text,
                    "utterance_intent": intent.__dict__,
                    "dialogue": [t.__dict__ for t in dialogue_turns],
                })

                backup_payload = {
                    "user_id": persona.data.get("id", f"U{user_index+1}"),
                    "step": step,
                    "public_state": public_state_mgr.to_dict(),
                    "action": action.__dict__,
                    "hidden_context": hidden.text,
                    "utterance_intent": intent.__dict__,
                    "dialogue": [t.__dict__ for t in dialogue_turns],
                }
                backup_mgr.maybe_backup(step, backup_payload)

        output_path = f"{cfg.output_dir}/simulation_output.xlsx"
        export_to_excel(output_path, {
            "public_state_log": logs.public_state_log,
            "private_state_log": logs.private_state_log,
            "dialogue_log": logs.dialogue_log,
            "self_rating_log": logs.self_rating_log,
            "third_party_rating_log": logs.third_party_rating_log,
        })
        return output_path
