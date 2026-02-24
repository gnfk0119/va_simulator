from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from src.schema import Environment, InteractionLog, StateChange
from utils.llm_client import query_llm
from utils.logger import get_logger


logger = get_logger(__name__)


class ObserverEvaluation(BaseModel):
    observer_rating: int
    observer_reason: str

class StateChangeDescription(BaseModel):
    description: str


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# _build_observability_index removed as requested


def _normalize_log_entry(entry: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(entry, dict):
        return None

    # Backward compatibility for old field names.
    if "concrete_action" not in entry and "visible_action" in entry:
        entry["concrete_action"] = entry.get("visible_action", "")
    if "latent_command" not in entry and "hidden_context" in entry:
        entry["latent_command"] = entry.get("hidden_context", "")

    try:
        return InteractionLog.parse_obj(entry).dict()
    except Exception:
        return None





def run_observer_evaluation(
    log_path: Path = Path("data/logs/simulation_log_full.json"),
    environment_path: Path = Path("data/generated/environment.json"),
    output_path: Path = Path("data/logs/evaluation_result.json"),
    model: Optional[str] = None,
) -> List[Dict[str, Any]]:
    if not log_path.exists():
        raise FileNotFoundError(f"Log file not found: {log_path}")

    logs = _load_json(log_path)
    if not isinstance(logs, list):
        raise ValueError(f"Invalid log format (expected list): {log_path}")
    # observability_index 제거
    updated_logs: List[Dict[str, Any]] = []
    skipped = 0

    for entry in logs:
        normalized = _normalize_log_entry(entry)
        if normalized is None:
            skipped += 1
            continue
        log = InteractionLog.parse_obj(normalized)

        # 1. With Context 평가
        if log.interaction_with_context:
            change_text_with = log.interaction_with_context.state_change_description or "상태 변화 없음"
            eval_with = _evaluate_single_interaction(
                change_text_with,
                log.interaction_with_context.command, log.interaction_with_context.va_response, model
            )
            log.interaction_with_context.observer_rating = eval_with.observer_rating
            log.interaction_with_context.observer_reason = eval_with.observer_reason

        # 2. Without Context 평가
        if log.interaction_without_context:
            change_text_without = log.interaction_without_context.state_change_description or "상태 변화 없음"
            eval_without = _evaluate_single_interaction(
                change_text_without,
                log.interaction_without_context.command, log.interaction_without_context.va_response, model
            )
            log.interaction_without_context.observer_rating = eval_without.observer_rating
            log.interaction_without_context.observer_reason = eval_without.observer_reason

        updated_logs.append(log.dict())

    _save_json(output_path, updated_logs)
    if skipped:
        logger.warning("Skipped %d incompatible log entries from %s", skipped, log_path)
    logger.info("Observer evaluation saved to %s", output_path)
    return updated_logs


def _evaluate_single_interaction(observable_text: str, command: str, response: str, model: Optional[str]) -> ObserverEvaluation:
    system_role = "당신은 관찰자 관점에서 평가합니다. 반드시 JSON만 출력하세요."
    prompt = f"""
        [관찰 가능한 단서]
        - 기기 상태 변화 조작 결과: {observable_text}
        - 주고받은 대화: 사용자="{command}" / VA="{response}"

        CCTV나 음성 기록으로 지켜보는 제 3자 입장에서 볼 때, 오직 이 2가지 정보만으로 판단했을 때 스마트홈 AI와 사용자의 상호작용이 얼마나 완벽하게 사용자의 요구를 처리한 것처럼 보입니까? (1-7점)
        반드시 JSON만 출력하세요.

        출력 형식:
        {{
        "observer_rating": 4,
        "observer_reason": "이유"
        }}
        """.strip()

    data = query_llm(prompt, system_role, model_schema=ObserverEvaluation, model=model)
    return ObserverEvaluation.parse_obj(data)
