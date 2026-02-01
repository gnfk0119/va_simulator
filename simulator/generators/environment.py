import json
import random
from typing import Any, Dict, List

from simulator.schemas import Environment


POWER_DEVICES = {
    "light", "tv", "fan", "heater", "air purifier", "coffee maker", "smart speaker",
    "microwave", "oven", "washing machine", "dryer", "vacuum cleaner", "dishwasher",
}


def _default_state(device: str) -> Dict[str, Any]:
    name = device.lower()
    if "thermostat" in name:
        return {"temp": 22, "mode": "auto"}
    if any(p in name for p in POWER_DEVICES):
        return {"power": "off"}
    return {"status": "idle"}


def _is_observable(device: str) -> bool:
    # Basic rule: device state is observable.
    return True


def _flatten_objects(profile: Dict[str, Any]) -> List[str]:
    objects = profile.get("What", {}).get("Objects", {})
    flattened: List[str] = []
    for _, items in objects.items():
        if isinstance(items, list):
            flattened.extend(items)
    return flattened


def _flatten_devices(profile: Dict[str, Any]) -> List[str]:
    appliances = profile.get("What", {}).get("Objects", {}).get("Appliances", [])
    tools = profile.get("What", {}).get("Objects", {}).get("Tools", [])
    return list(dict.fromkeys(appliances + tools))


def generate_environment(base_profile_path: str, num_rooms: int, num_devices: int, seed: int = 42) -> Environment:
    with open(base_profile_path, "r", encoding="utf-8") as f:
        profile = json.load(f)

    rng = random.Random(seed)
    room_pool = profile.get("Where", [])
    if not room_pool:
        room_pool = ["living_room", "kitchen", "bedroom", "bathroom"]

    rooms = []
    selected_rooms = room_pool[:num_rooms] if num_rooms <= len(room_pool) else room_pool

    devices_pool = _flatten_devices(profile)
    if not devices_pool:
        devices_pool = _flatten_objects(profile)

    rng.shuffle(devices_pool)
    selected_devices = devices_pool[:num_devices] if num_devices <= len(devices_pool) else devices_pool

    for room in selected_rooms:
        room_devices = rng.sample(selected_devices, k=min(len(selected_devices), max(1, len(selected_devices) // len(selected_rooms))))
        rooms.append({"name": room, "devices": room_devices})

    device_states = {d: _default_state(d) for d in selected_devices}
    observability = {d: _is_observable(d) for d in selected_devices}

    return Environment(
        raw_profile=profile,
        rooms=rooms,
        device_states=device_states,
        observability=observability,
    )
