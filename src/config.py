# src/config.py
import yaml
from pathlib import Path
from typing import Any, Dict

def load_config(config_path: str = "config.json") -> Dict[str, Any]:
    # JSON 대신 YAML 사용 권장 (가독성 위함)
    path = Path("config.yaml")
    if not path.exists():
        raise FileNotFoundError("config.yaml not found.")
    
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

# 전역에서 쓸 수 있게 로드
config = load_config()