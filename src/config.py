# src/config.py
import yaml
from pathlib import Path
from typing import Any, Dict

def load_config() -> Dict[str, Any]:
    path = Path("config.yaml")
    if not path.exists():
        # 파일이 없으면 기본값 반환 (안전장치)
        return {
            "simulation": {"num_profiles": 1, "model_name": "gpt-4o"},
            "paths": {
                "environment": "data/generated/environment.json",
                "avatar_dir": "data/generated/profiles",
                "log_dir": "data/logs"
            }
        }
    
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

# 전역 변수로 로드
config = load_config()