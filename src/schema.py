from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# --- Phase 1: Environment & Profile ---
class DeviceState(BaseModel):
    state_value: str = Field(..., description="현재 상태 (e.g., 'on', 'off', '24도')")
    is_observable: bool = Field(True, description="제 3자가 눈으로 상태를 확인할 수 있는지 여부")

    class Config:
        extra = "ignore"


class RoomObject(BaseModel):
    name: str
    properties: Dict[str, DeviceState]

    class Config:
        extra = "ignore"


class Environment(BaseModel):
    rooms: Dict[str, List[RoomObject]]

    class Config:
        extra = "ignore"


class ScheduleEvent(BaseModel):
    time: str
    activity: str

    class Config:
        extra = "ignore"


class AvatarProfile(BaseModel):
    name: str
    traits: str
    schedule: List[ScheduleEvent]

    class Config:
        extra = "ignore"


# --- Phase 2: Simulation Log ---
class StateChange(BaseModel):
    device_name: str
    property_name: str
    before: str
    after: str

    class Config:
        extra = "ignore"


class InteractionLog(BaseModel):
    time: str
    # Inputs for 1st Person
    visible_action: str
    hidden_context: str

    # Interaction
    command: str
    va_response: str
    state_changes: List[StateChange]

    # Evaluation
    self_rating: int
    self_reason: str

    # 3rd Person Evaluation (Filled in Phase 3)
    observer_rating: Optional[int] = None
    observer_reason: Optional[str] = None

    class Config:
        extra = "ignore"
