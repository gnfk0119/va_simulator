import json
from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class Config:
    data: Dict[str, Any]

    @property
    def seed(self) -> int:
        return int(self.data.get("seed", 42))

    @property
    def lang(self) -> str:
        return str(self.data.get("lang", "ko"))

    @property
    def num_users(self) -> int:
        return int(self.data.get("num_users", 1))

    @property
    def interaction_iteration(self) -> int:
        return int(self.data.get("interaction_iteration", 20))

    @property
    def schedule_days(self) -> int:
        return int(self.data.get("schedule_days", 7))

    @property
    def simulate_days(self) -> int:
        return int(self.data.get("simulate_days", 1))

    @property
    def day_to_simulate(self) -> str:
        return str(self.data.get("day_to_simulate", "Monday"))

    @property
    def max_actions_per_day(self) -> int:
        return int(self.data.get("max_actions_per_day", 20))

    @property
    def dialogue_max_turns(self) -> int:
        return int(self.data.get("dialogue_max_turns", 3))

    @property
    def utterance_threshold(self) -> float:
        return float(self.data.get("utterance_threshold", 0.6))

    @property
    def time_step_minutes(self) -> int:
        return int(self.data.get("time_step_minutes", 15))

    @property
    def backup(self) -> Dict[str, Any]:
        return dict(self.data.get("backup", {}))

    @property
    def output_dir(self) -> str:
        return str(self.data.get("output_dir", "data/output"))

    @property
    def environment(self) -> Dict[str, Any]:
        return dict(self.data.get("environment", {}))

    @property
    def llm(self) -> Dict[str, Any]:
        return dict(self.data.get("llm", {}))


def load_config(path: str) -> Config:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return Config(data)
