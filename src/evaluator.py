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


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _build_observability_index(environment: Environment) -> Dict[str, Dict[str, bool]]:
    index: Dict[str, Dict[str, bool]] = {}
    for _, room_objects in environment.rooms.items():
        for obj in room_objects:
            index[obj.name] = {k: v.is_observable for k, v in obj.properties.items()}
    return index


def _describe_change(change: StateChange) -> str:
    prop = change.property_name
    if prop == "power":
        if change.after == "on":
            return f"{change.device_name}가 켜졌다"
        if change.after == "off":
            return f"{change.device_name}가 꺼졌다"
    if prop == "temperature":
        return f"{change.device_name}의 온도가 {change.after}로 바뀌었다"
    if prop == "brightness":
        return f"{change.device_name}의 밝기가 {change.after}로 바뀌었다"
    if prop == "volume":
        return f"{change.device_name}의 볼륨이 {change.after}로 바뀌었다"
    return f"{change.device_name}의 {prop}이(가) {change.after}로 바뀌었다"


def _observable_change_text(
    changes: List[StateChange],
    observability_index: Dict[str, Dict[str, bool]],
) -> str:
    visible_changes = []
    for change in changes:
        is_observable = observability_index.get(change.device_name, {}).get(
            change.property_name,
            False,
        )
        if is_observable:
            visible_changes.append(_describe_change(change))

    if not visible_changes:
        return "관측 가능한 변화 없음"
    return "; ".join(visible_changes)


def run_observer_evaluation(
    log_path: Path = Path("data/logs/simulation_log_full.json"),
    environment_path: Path = Path("data/generated/environment.json"),
    output_path: Path = Path("data/logs/evaluation_result.json"),
    model: Optional[str] = None,
) -> List[Dict[str, Any]]:
    if not log_path.exists():
        raise FileNotFoundError(f"Log file not found: {log_path}")

    logs = _load_json(log_path)
    env_data = _load_json(environment_path)
    environment = Environment.parse_obj(env_data)
    observability_index = _build_observability_index(environment)

    updated_logs: List[Dict[str, Any]] = []

    for entry in logs:
        log = InteractionLog.parse_obj(entry)
        observable_text = _observable_change_text(log.state_changes, observability_index)

        system_role = "당신은 관찰자 관점에서 평가합니다. 반드시 JSON만 출력하세요."
        prompt = f"""
            [관찰 데이터]
            - 행동: {log.visible_action}
            - 관측된 결과: {observable_text}
            - 대화: 사용자="{log.command}" / VA="{log.va_response}"

            CCTV로 지켜보는 제 3자 입장에서, 이 상호작용이 얼마나 만족스러워 보입니까? (1-7점)
            반드시 JSON만 출력하세요.

            출력 형식:
            {{
            "observer_rating": 1,
            "observer_reason": "이유"
            }}
            """.strip()

        data = query_llm(prompt, system_role, model_schema=ObserverEvaluation, model=model)
        evaluation = ObserverEvaluation.parse_obj(data)

        log.observer_rating = evaluation.observer_rating
        log.observer_reason = evaluation.observer_reason
        updated_logs.append(log.dict())

    _save_json(output_path, updated_logs)
    logger.info("Observer evaluation saved to %s", output_path)
    return updated_logs
