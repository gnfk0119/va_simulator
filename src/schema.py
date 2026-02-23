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
    type_name: str = Field(default="A", description="평면도 타입 (A, B, C, D)")
    rooms: Dict[str, List[RoomObject]]

    class Config:
        extra = "ignore"


class ScheduleEvent(BaseModel):
    time: str
    activity: str
    is_at_home: bool = Field(default=True, description="집 안에 있는지 여부")

    class Config:
        extra = "ignore"


class MemberProfile(BaseModel):
    member_id: str
    name: str
    role: str
    age: int
    economic_status: str
    monthly_income: str
    traits: str
    schedule: List[ScheduleEvent]

    class Config:
        extra = "ignore"


class FamilyProfile(BaseModel):
    family_id: str
    members: List[MemberProfile]

    class Config:
        extra = "ignore"


# --- Shared Memory ---
class MemoryItem(BaseModel):
    time: str
    member_id: str
    description: str
    decay_weight: float = 1.0
    shared_with: List[str] = Field(default_factory=list, description="이 기억을 공유받은 member_id 리스트")

    class Config:
        extra = "ignore"


# --- Phase 2: Action & Context ---
class ActionContext(BaseModel):
    concrete_action: str = Field(..., description="구체화된 행동 (예: 거실 소파에 앉아 조용히 낮잠을 잠)")
    latent_command: str = Field(..., description="잠재 명령 - 현재 상황에서 VA에게 할 실제 명령어 (예: 조용히 안방 에어컨 틀어줘)")
    needs_voice_command: bool = Field(
        ...,
        description=(
            "현재 상황을 고려했을 때 VA에게 명령을 내릴 필요가 있거나 "
            "내릴 수 있는 상황인지 여부"
        ),
    )

    class Config:
        extra = "ignore"


# --- Phase 2 & 3: Simulation Log ---
class StateChange(BaseModel):
    device_name: str
    property_name: str
    before: str
    after: str

    class Config:
        extra = "ignore"


class InteractionResult(BaseModel):
    command: str
    va_response: str
    state_changes: List[StateChange]
    state_change_description: Optional[str] = None
    self_rating: int
    self_reason: str
    observer_rating: Optional[int] = None
    observer_reason: Optional[str] = None

    class Config:
        extra = "ignore"


class InteractionLog(BaseModel):
    simulation_id: str
    timestamp: str
    family_id: str
    environment_type: str
    member_id: str
    member_name: str
    member_role: str
    member_age: int

    # Inputs for 1st Person
    location: str
    concrete_action: str
    latent_command: str
    shared_memory_refs: List[str] = Field(default_factory=list)

    # Interactions
    interaction_with_context: Optional[InteractionResult] = None
    interaction_without_context: Optional[InteractionResult] = None

    class Config:
        extra = "ignore"

