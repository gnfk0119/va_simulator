# src/config.py
import yaml
from pathlib import Path
from typing import Any, Dict

def load_config() -> Dict[str, Any]:
    path = Path("config.yaml")
    if not path.exists():
        # 파일이 없으면 기본값 반환 (안전장치)
        return {
            "run": {"name": "default_run_A"},
            "simulation": {"period": "일주일 전체", "num_profiles": 1, "step_minutes": 15},
            "evaluation": {"gap_threshold": 2},
            "memory": {"decay_per_hour": 0.05, "floor": 0.2},
            "models": {
                "generator_env": {"provider": "openai", "model": "gpt-4o"},
                "generator_family": {"provider": "openai", "model": "gpt-4o"},
                "schedule": {"provider": "openai", "model": "gpt-4o"},
                "action": {"provider": "openai", "model": "gpt-4o-mini"},
                "request": {"provider": "openai", "model": "gpt-4o-mini"},
                "va_c": {"provider": "openai", "model": "gpt-4o-mini"},
                "va_r_classifier": {"provider": "gemini", "model": "gemini-3-flash"},
                "va_r_response": {"provider": "openai", "model": "gpt-4o-mini"},
                "self_eval": {"provider": "openai", "model": "gpt-4o"},
                "third_eval": {"provider": "openai", "model": "gpt-4o"}
            },
            "family_generation": {
                "mode": "prompt",
                "random_constraints": {
                    "size_min": 2,
                    "size_max": 4,
                    "location": "수도권 및 시 지역",
                    "min_monthly_income_krw": 4000000
                },
                "prompt_instruction": "2인 30대 부부 + 고등학생 여학생 자녀",
                "template_name": "default_couple"
            }
        }
    
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

# 전역 변수로 로드
config = load_config()