from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from src.schema import Environment, RoomObject, StateChange


POWER_ON_KEYWORDS = ["켜", "켜줘", "켜 줘", "on", "turn on", "시작"]
POWER_OFF_KEYWORDS = ["꺼", "끄", "꺼줘", "꺼 줘", "off", "turn off", "종료"]

PROPERTY_KEYWORDS = {
    "brightness": ["밝기", "조도"],
    "temperature": ["온도", "도", "난방", "냉방"],
    "volume": ["볼륨", "음량", "소리"],
    "channel": ["채널"],
    "mode": ["모드", "풍량", "세기"],
}


def _normalize(text: str) -> str:
    return text.lower().strip()


def _extract_number(text: str) -> Optional[str]:
    match = re.search(r"(-?\d+(?:\.\d+)?)", text)
    if match:
        return match.group(1)
    return None


def _iter_objects(environment: Environment) -> List[RoomObject]:
    objects: List[RoomObject] = []
    for _, room_objects in environment.rooms.items():
        objects.extend(room_objects)
    return objects


def _find_target_object(command: str, environment: Environment) -> Optional[RoomObject]:
    command_norm = _normalize(command)
    candidates = []
    for obj in _iter_objects(environment):
        if _normalize(obj.name) in command_norm:
            candidates.append(obj)

    if candidates:
        candidates.sort(key=lambda o: len(o.name), reverse=True)
        return candidates[0]

    # Fallbacks for common device types
    type_hints = {
        "조명": ["등", "조명", "라이트"],
        "tv": ["tv", "티비", "텔레비전"],
        "에어컨": ["에어컨", "냉방"],
        "스피커": ["스피커", "음악", "소리"],
        "보일러": ["보일러", "난방"],
        "커튼": ["커튼", "블라인드"],
    }

    for obj in _iter_objects(environment):
        for _, keywords in type_hints.items():
            if any(k in command_norm for k in keywords):
                if any(k in _normalize(obj.name) for k in keywords):
                    return obj
    return None


def _detect_power_state(command: str) -> Optional[str]:
    command_norm = _normalize(command)
    if any(k in command_norm for k in POWER_ON_KEYWORDS):
        return "on"
    if any(k in command_norm for k in POWER_OFF_KEYWORDS):
        return "off"
    return None


def _detect_property(command: str, obj: RoomObject) -> Tuple[Optional[str], Optional[str]]:
    command_norm = _normalize(command)

    power_state = _detect_power_state(command)
    if power_state and "power" in obj.properties:
        return "power", power_state

    number = _extract_number(command_norm)
    for prop, keywords in PROPERTY_KEYWORDS.items():
        if prop in obj.properties and any(k in command_norm for k in keywords):
            if number:
                if prop == "temperature":
                    return prop, f"{number}도"
                if prop == "brightness":
                    return prop, f"{number}%"
                if prop == "volume":
                    return prop, f"{number}"
                return prop, number
            # No number, still a request (e.g., "밝기 올려")
            return prop, "조정됨"

    return None, None


def _apply_change(obj: RoomObject, prop: str, value: str) -> StateChange:
    before = obj.properties[prop].state_value
    obj.properties[prop].state_value = value
    return StateChange(
        device_name=obj.name,
        property_name=prop,
        before=before,
        after=value,
    )


def execute_command(command: str, environment: Environment) -> Tuple[str, List[StateChange]]:
    """Rule-based virtual assistant executor.

    Returns a natural language response and list of state changes.
    """
    target = _find_target_object(command, environment)
    if not target:
        return "죄송해요. 어떤 기기를 조작해야 할지 모르겠어요.", []

    prop, value = _detect_property(command, target)
    if not prop or value is None:
        return f"죄송해요. '{target.name}'에서 어떤 설정을 바꿔야 할지 알기 어렵습니다.", []

    if prop not in target.properties:
        return f"죄송해요. '{target.name}'에는 '{prop}' 설정이 없어요.", []

    change = _apply_change(target, prop, value)

    if prop == "power":
        if value == "on":
            response = f"알겠습니다. {target.name}를 켰어요."
        else:
            response = f"알겠습니다. {target.name}를 껐어요."
    else:
        response = f"알겠습니다. {target.name}의 {prop}을 {value}로 설정했어요."

    return response, [change]
