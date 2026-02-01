from typing import Any, Dict, List


class LogStore:
    def __init__(self) -> None:
        self.public_state_log: List[Dict[str, Any]] = []
        self.private_state_log: List[Dict[str, Any]] = []
        self.dialogue_log: List[Dict[str, Any]] = []
        self.self_rating_log: List[Dict[str, Any]] = []
        self.third_party_rating_log: List[Dict[str, Any]] = []

    def add_public(self, row: Dict[str, Any]) -> None:
        self.public_state_log.append(row)

    def add_private(self, row: Dict[str, Any]) -> None:
        self.private_state_log.append(row)

    def add_dialogue(self, row: Dict[str, Any]) -> None:
        self.dialogue_log.append(row)

    def add_self_rating(self, row: Dict[str, Any]) -> None:
        self.self_rating_log.append(row)

    def add_third_rating(self, row: Dict[str, Any]) -> None:
        self.third_party_rating_log.append(row)
