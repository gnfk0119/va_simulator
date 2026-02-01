import json
from typing import Any, Dict, List


class MemoryStore:
    def __init__(self) -> None:
        self._events: List[Dict[str, Any]] = []

    def add(self, event: Dict[str, Any]) -> None:
        self._events.append(event)

    def last(self, n: int = 5) -> List[Dict[str, Any]]:
        if n <= 0:
            return []
        return self._events[-n:]

    def to_json(self, n: int = 5) -> str:
        return json.dumps(self.last(n), ensure_ascii=False, indent=2)
