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
    if "seed_command" not in entry and "hidden_context" in entry:
        entry["seed_command"] = entry.get("hidden_context", "")

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

        for attr_name in ["interaction_wc_vac", "interaction_wc_var", "interaction_woc_vac", "interaction_woc_var"]:
            interaction = getattr(log, attr_name, None)
            if interaction:
                change_text = interaction.state_change_description or "상태 변화 없음"
                eval_obj = _evaluate_single_interaction(
                    change_text,
                    interaction.command,
                    interaction.va_response,
                    model
                )
                interaction.observer_rating = eval_obj.observer_rating
                interaction.observer_reason = eval_obj.observer_reason

        updated_logs.append(log.dict())

    _save_json(output_path, updated_logs)
    if skipped:
        logger.warning("Skipped %d incompatible log entries from %s", skipped, log_path)
    logger.info("Observer evaluation saved to %s", output_path)
    return updated_logs


def _evaluate_single_interaction(observable_text: str, command: str, response: str, model: Optional[str]) -> ObserverEvaluation:
    system_role = "당신은 관찰자 관점에서 평가합니다. 반드시 JSON만 출력하세요."
    prompt = Path("prompts/evaluator_observer.txt").read_text(encoding="utf-8").format(
        observable_text=observable_text,
        command=command,
        response=response
    )

    data = query_llm(prompt, system_role, model_schema=ObserverEvaluation, model=model)
    return ObserverEvaluation.parse_obj(data)
