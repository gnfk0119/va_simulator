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
    bio: str
    schedule: List[ScheduleEvent]

    class Config:
        extra = "ignore"


class FamilyProfile(BaseModel):
    family_id: str
    members: List[MemberProfile]

    class Config:
        extra = "ignore"


# --- Phase 1: Generated Demographics ---
class GeneratedMember(BaseModel):
    name: str = Field(..., description="구성원 이름 (예: 김철수)")
    role: str = Field(..., description="가계에서의 역할 (예: 아빠(가구주), 엄마(배우자), 아들(자녀))")
    age: int = Field(..., description="나이 (0 ~ 100)")
    gender: str = Field(..., description="'남성' 또는 '여성'")
    economic_status: str = Field(..., description="경제활동 상태 (예: 재직중, 학생, 주부 등)")
    monthly_income: str = Field(..., description="가구 소득 수준 문자열 (예: 500만원 이상)")
    bio: str = Field(..., description="해당 구성원의 성격과 전자기기 활용 습관 등 3문장 이상의 구체적인 인물 소개")
    is_working: bool = Field(..., description="현재 직장/경제활동을 하는지 여부")

    class Config:
        extra = "ignore"

class GeneratedFamily(BaseModel):
    location: str = Field(..., description="거주지 (예: 수도권 및 시 지역)")
    members: List[GeneratedMember]

    class Config:
        extra = "ignore"


# --- Shared Memory ---
class MemoryItem(BaseModel):
    timestamp: str
    log_type: str = Field(..., description="action 또는 interaction")
    content: str
    weight: float = 1.0

    class Config:
        extra = "ignore"


# --- Phase 2: Action & Context ---
class ActionContext(BaseModel):
    quarterly_activity: str = Field(..., description="15분 단위의 구체적인 활동 요약")
    location: str = Field(..., description="현재 위치 (예: 거실, 안방, 집 밖 등)")
    is_at_home: bool = Field(..., description="현재 인물이 집 안에 있는지 여부")
    concrete_action: str = Field(..., description="구체화된 3문장 이상의 순차적인 행동 묘사")
    wc_command: str = Field(..., description="명령 상황이나 맥락이 포함된 음성 명령 (예: 아이가 자니까 TV 볼륨 줄여줘)")
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
    hourly_activity: str
    quarterly_activity: str
    concrete_action: str
    seed_command: str
    shared_memory_refs: List[str] = Field(default_factory=list)

    # Interactions (4-cell Matrix)
    interaction_wc_vac: Optional[InteractionResult] = None
    interaction_wc_var: Optional[InteractionResult] = None
    interaction_woc_vac: Optional[InteractionResult] = None
    interaction_woc_var: Optional[InteractionResult] = None

    class Config:
        extra = "ignore"
