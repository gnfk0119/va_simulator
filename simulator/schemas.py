from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Environment:
    raw_profile: Dict[str, Any]
    rooms: List[Dict[str, Any]]
    device_states: Dict[str, Any]
    observability: Dict[str, bool]


@dataclass
class Persona:
    data: Dict[str, Any]


@dataclass
class ScheduleWeek:
    data: Dict[str, Any]

    def get_day(self, day_name: str) -> List[Dict[str, Any]]:
        week = self.data.get("week", {})
        return list(week.get(day_name, []))


@dataclass
class Action:
    time: str
    location: str
    visible_action: str
    device_targets: List[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class HiddenContext:
    text: str


@dataclass
class UtteranceIntent:
    score: float
    threshold: float
    should_speak: bool
    rationale: str


@dataclass
class DialogueTurn:
    turn_id: int
    speaker: str
    text: str


@dataclass
class Rating:
    score: int
    reason: str


@dataclass
class PublicState:
    time: str
    location: str
    visible_action: str
    device_state: Dict[str, Any]
    available_devices: List[str]


@dataclass
class PrivateState:
    hidden_context: str


@dataclass
class SimulationRecord:
    user_id: str
    action: Action
    hidden_context: HiddenContext
    utterance_intent: UtteranceIntent
    dialogue: List[DialogueTurn] = field(default_factory=list)
    self_ratings: List[Rating] = field(default_factory=list)
    third_party_ratings: List[Rating] = field(default_factory=list)
