from pathlib import Path


class PromptLoader:
    def __init__(self, prompts_dir: str = "prompts") -> None:
        self._dir = Path(prompts_dir)

    def load(self, name: str) -> str:
        path = self._dir / name
        return path.read_text(encoding="utf-8")
