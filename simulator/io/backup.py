import json
from pathlib import Path
from typing import Any, Dict


class BackupManager:
    def __init__(self, mode: str, every_n: int, directory: str) -> None:
        self._mode = mode
        self._every_n = max(1, every_n)
        self._dir = Path(directory)
        self._dir.mkdir(parents=True, exist_ok=True)

    def maybe_backup(self, step: int, payload: Dict[str, Any]) -> None:
        if self._mode == "off":
            return
        if self._mode == "every_step" or (step % self._every_n == 0):
            path = self._dir / f"step_{step:04d}.json"
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
