from dataclasses import asdict
from typing import Any, Dict, List

from simulator.schemas import PublicState, Action


class PublicStateManager:
    def __init__(self, device_state: Dict[str, Any], available_devices: List[str], start_time: str) -> None:
        self._state = PublicState(
            time=start_time,
            location="",
            visible_action="",
            device_state=device_state,
            available_devices=available_devices,
        )

    def update(self, action: Action) -> None:
        self._state.time = action.time
        self._state.location = action.location
        self._state.visible_action = action.visible_action

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self._state)

    @property
    def state(self) -> PublicState:
        return self._state
