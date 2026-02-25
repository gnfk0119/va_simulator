import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

from pydantic import BaseModel

from src.schema import (
    FamilyProfile, Environment, InteractionLog, StateChange, 
    ActionContext, InteractionResult, MemoryItem
)
from src.config import config
from src.va_baseline import execute_command as va_c_execute
from src.va_r import execute_command as va_r_execute
from utils.llm_client import LLMError, query_llm
from utils.logger import get_logger

logger = get_logger(__name__)

OUT_OF_HOME_KEYWORDS = [
    "출근",
    "퇴근",
    "등교",
    "하교",
    "통학",
    "통근",
    "이동",
    "외출",
    "회사",
    "학교",
    "구직",
    "창업",
    "수입노동",
]

NO_COMMAND_KEYWORDS = [
    "수면",
    "취침",
    "휴식",
    "명상",
    "샤워",
    "개인위생",
]

class CommandOutput(BaseModel):
    command: str

class SelfEvaluation(BaseModel):
    self_rating: int
    self_reason: str

def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def _save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _format_state_changes(changes: List[StateChange]) -> str:
    if not changes:
        return "변화 없음"
    return "; ".join([f"{c.device_name}.{c.property_name}: {c.before}->{c.after}" for c in changes])


def _is_sleeping_activity(activity: str) -> bool:
    text = (activity or "").strip()
    return any(keyword in text for keyword in ["수면", "취침", "낮잠"])


def _infer_is_at_home_from_activity(activity: str) -> bool:
    text = (activity or "").strip()
    if not text:
        return True
    return not any(keyword in text for keyword in OUT_OF_HOME_KEYWORDS)


def _parse_schedule_slot(time_str: str) -> Optional[tuple[int, int]]:
    raw = (time_str or "").strip()
    if not raw:
        return None

    for fmt in ("%m-%d %H:%M", "%Y-%m-%d %H:%M"):
        try:
            dt = datetime.strptime(raw, fmt)
            day = dt.day
            if 1 <= day <= 7:
                return (day, dt.hour)
        except ValueError:
            pass

    day_match = re.match(r"^Day_(\d{1,2})\s+(\d{1,2}):(\d{2})$", raw)
    if day_match:
        day = int(day_match.group(1))
        hour = int(day_match.group(2))
        if 1 <= day <= 7 and 0 <= hour <= 23:
            return (day, hour)

    return None


def _build_bio_from_legacy(member: Dict[str, Any]) -> str:
    name = str(member.get("name", "구성원")).strip() or "구성원"
    role = str(member.get("role", "가족 구성원")).strip() or "가족 구성원"
    age = member.get("age", "성인")
    economic_status = str(member.get("economic_status", "일상 생활")).strip() or "일상 생활"
    traits = str(member.get("traits", "")).strip()

    sentence_1 = f"{name}는 {age}세 {role}로, 현재 {economic_status} 상태에서 생활한다."
    sentence_2 = f"평소에는 하루 리듬을 크게 벗어나지 않고 집안과 외부 일정을 균형 있게 관리한다."
    sentence_3 = (
        f"개인 성향은 {traits}으로 나타나며, 상황에 따라 생활 패턴이 비교적 뚜렷하게 드러난다."
        if traits
        else "개인 성향은 차분하고 실용적인 편으로, 상황에 맞춰 일정을 조정하는 습관이 있다."
    )
    sentence_4 = "집에서는 필요할 때 생활 환경을 조절하기 위해 스마트홈 기기를 자연스럽게 활용하는 편이다."
    return " ".join([sentence_1, sentence_2, sentence_3, sentence_4])


def _normalize_member_payload(member: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(member)
    bio = str(normalized.get("bio", "")).strip()
    if not bio:
        normalized["bio"] = _build_bio_from_legacy(normalized)
    normalized.pop("traits", None)

    schedule_items = normalized.get("schedule", [])
    slot_map: Dict[tuple[int, int], Dict[str, Any]] = {}

    if isinstance(schedule_items, list):
        for event in schedule_items:
            if not isinstance(event, dict):
                continue

            raw_time = event.get("time") or event.get("datetime")
            slot = _parse_schedule_slot(str(raw_time))
            if slot is None:
                continue

            activity = str(event.get("activity", "")).strip() or "수면 혹은 휴식"
            is_at_home = event.get("is_at_home")
            if not isinstance(is_at_home, bool):
                is_at_home = _infer_is_at_home_from_activity(activity)

            if slot not in slot_map:
                slot_map[slot] = {"activity": activity, "is_at_home": bool(is_at_home)}

    normalized_schedule: List[Dict[str, Any]] = []
    last_activity = "수면 혹은 휴식"
    last_is_at_home = True

    period = config["simulation"].get("period", "일주일 전체")
    period = config["simulation"].get("period", "일주일 전체")
    if period == "일주일 전체":
        day_range = range(1, 8)
    elif period == "평일만":
        day_range = range(1, 2)
    elif period == "금토일":
        day_range = range(5, 8)
    else: # "일요일"
        day_range = range(7, 8)

    start_h = config["simulation"].get("start_hour", 0)
    end_h = config["simulation"].get("end_hour", 24)

    for day in day_range:
        for hour in range(start_h, end_h):
            slot = slot_map.get((day, hour))
            if slot:
                last_activity = slot["activity"]
                last_is_at_home = slot["is_at_home"]

            normalized_schedule.append({
                "time": f"09-{day:02d} {hour:02d}:00",
                "activity": last_activity,
                "is_at_home": bool(last_is_at_home),
            })

    normalized["schedule"] = normalized_schedule
    return normalized


def _normalize_family_payload(raw_family: Dict[str, Any]) -> Dict[str, Any]:
    family = dict(raw_family)
    members = family.get("members", [])
    if not isinstance(members, list):
        family["members"] = []
        return family

    family["members"] = [
        _normalize_member_payload(member) for member in members if isinstance(member, dict)
    ]
    return family


def _fallback_seed_command(activity: str) -> str:
    text = (activity or "").strip()
    if not text:
        return ""
    if any(k in text for k in NO_COMMAND_KEYWORDS):
        return ""
    if "청소" in text:
        return "로봇청소기 청소 시작해줘"
    if "요리" in text or "식사" in text:
        return "주방 조명 켜줘"
    if "공부" in text or "업무" in text:
        return "책상 조명 켜줘"
    if "TV" in text or "시청" in text:
        return "거실 TV 켜줘"
    if "세탁" in text:
        return "세탁기 시작해줘"
    return "거실 메인 조명 켜줘"


def _build_fallback_action_context(hourly_activity: str) -> ActionContext:
    return ActionContext(
        quarterly_activity=f"{hourly_activity} 중단",
        location="거실",
        is_at_home=True,
        concrete_action="알 수 없는 행동",
        wc_command="아이가 자니까 TV 볼륨 줄여줘",
        needs_voice_command=False
    )


def _normalize_existing_log_entry(entry: Any) -> Optional[Dict[str, Any]]:
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


class MemorySystem:
    def __init__(self):
        # member_id -> List[MemoryItem]
        self.memories: Dict[str, List[MemoryItem]] = {}

    def add_memory(self, timestamp: str, member_id: str, log_type: str, content: str):
        if member_id not in self.memories:
            self.memories[member_id] = []
        self.memories[member_id].append(MemoryItem(
            timestamp=timestamp,
            log_type=log_type,
            content=content,
            weight=1.0
        ))

    def add_shared_memory(self, timestamp: str, log_type: str, content: str, shared_with: List[str]):
        for m_id in shared_with:
            self.add_memory(timestamp, m_id, log_type, content)

    def update_decay(self):
        # 1시간 루프 등 특정 시점에 호출되어 모든 메모리의 decay를 줄임
        for mem_list in self.memories.values():
            for m in mem_list:
                m.weight = max(0.2, round(m.weight - 0.05, 2))

    def get_context_for_member(self, member_id: str) -> str:
        my_mems = self.memories.get(member_id, [])
        if not my_mems:
            return "관찰되는 다른 가족의 행동이나 최근 상황 없음."
        
        my_mems.sort(key=lambda x: x.weight, reverse=True)
        # 상위 8개 정도 보여주기
        lines = [f" - [{m.timestamp}] [{m.log_type}] {m.content} (기억가중치: {m.weight})" for m in my_mems[:8]]
        return "\n".join(lines)


class SimulationEngine:
    def __init__(
        self,
        environment_path: Path = Path("data/generated/environment.json"),
        family_path: Path = Path("data/generated/family_profile.json"),
        log_path: Path = Path("data/logs/simulation_log_full.json"),
        model_seq: Optional[str] = None,
        model_va: Optional[str] = None,
    ) -> None:
        self.environment_path = environment_path
        self.family_path = family_path
        self.log_path = log_path
        self.model_seq = model_seq
        self.model_va = model_va

        env_data = _load_json(environment_path)
        family_data = _normalize_family_payload(_load_json(family_path))

        self.environment = Environment.parse_obj(env_data)
        self.family = FamilyProfile.parse_obj(family_data)
        self.memory = MemorySystem()

    def run(self) -> List[Dict[str, Any]]:
        logs = self._load_existing_logs()
        
        # 1. 1시간 단위 스케줄을 15분 단위로 쪼개어 Timeline 병합
        timeline = []
        # '09-01' 같은 가상 날짜가 들어있다고 가정 (이미 generator에서 붙여넣음)
        # 만약 형식이 '09-01 08:00' 이라면 이를 datetime으로 파싱해야 함
        
        # 파싱 오류를 막기 위해 연도를 붙여서 변환 처리
        current_year = datetime.now().year
        
        for member in self.family.members:
            for event in member.schedule:
                # event.time format: "09-01 08:00"
                try:
                    dt_str = f"{current_year}-{event.time}"
                    base_time = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
                except ValueError:
                    # Fallback 처리
                    base_time = datetime.now()
                for m_offset in [0, 15, 30, 45]:
                    curr_time = base_time + timedelta(minutes=m_offset)
                    timeline.append({
                        "time_obj": curr_time,
                        "time": curr_time.strftime("%m-%d %H:%M"),
                        "member": member,
                        "hourly_activity": event.activity,
                        "is_at_home": getattr(event, "is_at_home", True)
                    })
        
        timeline.sort(key=lambda x: x["time_obj"])
        
        current_hour_str = None
        for step in timeline:
            step_time = step["time"]
            # 시(Hour)가 바뀌면 메모리 감쇠 적용
            hour_str = step_time[:14] # "MM-DD HH"
            if current_hour_str and hour_str != current_hour_str:
                self.memory.update_decay()
            current_hour_str = hour_str
            
            if not step["is_at_home"]:
                # 외출 중이면 시뮬레이션 생략하되 로그는 남김
                log_entry = self.run_step(step, skip_reason="외출 중")
            elif _is_sleeping_activity(step["hourly_activity"]):
                # 수면 중이면 시뮬레이션 생략하되 로그는 남김
                log_entry = self.run_step(step, skip_reason="수면 중")
            else:
                log_entry = self.run_step(step)
                
            if log_entry:
                logs.append(log_entry)
                _save_json(self.log_path, logs)

        # 메모리 기록도 별도 저장
        memory_out_path = self.log_path.parent / "memory_history.json"
        
        flat_memories = []
        for v_id, m_list in self.memory.memories.items():
            for m in m_list:
                flat_memories.append({"member_id": v_id, **m.dict()})
        _save_json(memory_out_path, flat_memories)

        return logs

    def run_step(self, step: dict, skip_reason: Optional[str] = None) -> Optional[Dict[str, Any]]:
        time = step["time"]
        hourly_activity = step["hourly_activity"]
        member = step["member"]
        
        # 메모리 불러오기
        mem_context = self.memory.get_context_for_member(member.member_id)

        # 건너뛰기 처리 (외출, 수면 등)
        if skip_reason:
            print(f"⏭️ [SKIP] {time} {member.name}: {hourly_activity} ({skip_reason})")
            log = InteractionLog(
                simulation_id=f"sim_{self.family.family_id}",
                timestamp=time,
                family_id=self.family.family_id,
                environment_type=self.environment.type_name,
                member_id=member.member_id,
                member_name=member.name,
                member_role=member.role,
                member_age=member.age,
                location="집 밖" if skip_reason == "외출 중" else "침실",
                hourly_activity=hourly_activity,
                quarterly_activity=f"{hourly_activity} 진행 중" if skip_reason != "외출 중" else "외부 활동 중",
                concrete_action="스마트홈 기기 조작 없음" if skip_reason != "외출 중" else "집 안에 없음",
                seed_command="",
                shared_memory_refs=[mem_context],
                interaction_wc_vac=None,
                interaction_wc_var=None,
                interaction_woc_vac=None,
                interaction_woc_var=None
            )
            return log.dict()

        # 1. 15분 단위 구체적 행동(Concrete Action) 및 잠재 명령(Latent Command) 생성
        action_context = self._generate_action_context(time, hourly_activity, member, mem_context)
        
        # 2. 모든 15분 단위 행동은 메모리(상태 관찰 로그)에 무조건 저장
        shared_list = [m.member_id for m in self.family.members]
        mem_desc = f"[{member.name}] {action_context.concrete_action}"
        self.memory.add_shared_memory(time, "action", mem_desc, shared_list)

        if not action_context.needs_voice_command:
            print(f"⏭️ [SKIP] {time} {member.name}: {action_context.concrete_action} (명령 불필요)")
            log = InteractionLog(
                simulation_id=f"sim_{self.family.family_id}",
                timestamp=time,
                family_id=self.family.family_id,
                environment_type=self.environment.type_name,
                member_id=member.member_id,
                member_name=member.name,
                member_role=member.role,
                member_age=member.age,
                location=action_context.location,
                hourly_activity=hourly_activity,
                quarterly_activity=action_context.quarterly_activity,
                concrete_action=action_context.concrete_action,
                seed_command=action_context.wc_command,
                shared_memory_refs=[mem_context],
                interaction_wc_vac=None,
                interaction_wc_var=None,
                interaction_woc_vac=None,
                interaction_woc_var=None
            )
            return log.dict()

        print(f"🗣️ [ACT] {time} {member.name}: {action_context.concrete_action} (잠재: {action_context.wc_command})")

        # 3. Request Generation (With Context / Without Context)
        cmd_with = action_context.wc_command
        cmd_without = self._generate_woc_command(cmd_with, action_context.concrete_action)

        # VA 호출 자체도 메모리에 기록
        self.memory.add_shared_memory(time, "interaction", f"[{member.name}] VA에게 '{cmd_with}'라고 음성 명령함", shared_list)

        # 4. 4-Cell Matrix Simulation
        
        # 1) WC x VA_C (Baseline, persists state)
        res_wc_vac, changes_wc_vac, desc_wc_vac = va_c_execute(cmd_with, self.environment, model=self.model_va)
        eval_wc_vac = self._self_evaluate(action_context.wc_command, cmd_with, res_wc_vac, changes_wc_vac, mem_context)
        
        # 2) WC x VA_R (Classifier, isolated)
        env_copy_wc_var = Environment.parse_obj(self.environment.dict())
        res_wc_var, changes_wc_var, desc_wc_var = va_r_execute(cmd_with, env_copy_wc_var)
        eval_wc_var = self._self_evaluate(action_context.wc_command, cmd_with, res_wc_var, changes_wc_var, mem_context)

        # 3) WOC x VA_C (Baseline, isolated)
        env_copy_woc_vac = Environment.parse_obj(self.environment.dict())
        res_woc_vac, changes_woc_vac, desc_woc_vac = va_c_execute(cmd_without, env_copy_woc_vac, model=self.model_va)
        eval_woc_vac = self._self_evaluate(action_context.wc_command, cmd_without, res_woc_vac, changes_woc_vac, mem_context)
        
        # 4) WOC x VA_R (Classifier, isolated)
        env_copy_woc_var = Environment.parse_obj(self.environment.dict())
        res_woc_var, changes_woc_var, desc_woc_var = va_r_execute(cmd_without, env_copy_woc_var)
        eval_woc_var = self._self_evaluate(action_context.wc_command, cmd_without, res_woc_var, changes_woc_var, mem_context)

        # 5. 메모리 업데이트(위에서 이미 처리 완료됨)

        # 6. 로그 생성
        log = InteractionLog(
            simulation_id=f"sim_{self.family.family_id}",
            timestamp=time,
            family_id=self.family.family_id,
            environment_type=self.environment.type_name,
            member_id=member.member_id,
            member_name=member.name,
            member_role=member.role,
            member_age=member.age,
            location=action_context.location,
            hourly_activity=hourly_activity,
            quarterly_activity=action_context.quarterly_activity,
            concrete_action=action_context.concrete_action,
            seed_command=action_context.wc_command,
            shared_memory_refs=[mem_context],
            interaction_wc_vac=InteractionResult(
                command=cmd_with,
                va_response=res_wc_vac,
                state_changes=changes_wc_vac,
                state_change_description=desc_wc_vac,
                self_rating=eval_wc_vac.self_rating,
                self_reason=eval_wc_vac.self_reason,
            ),
            interaction_wc_var=InteractionResult(
                command=cmd_with,
                va_response=res_wc_var,
                state_changes=changes_wc_var,
                state_change_description=desc_wc_var,
                self_rating=eval_wc_var.self_rating,
                self_reason=eval_wc_var.self_reason,
            ),
            interaction_woc_vac=InteractionResult(
                command=cmd_without,
                va_response=res_woc_vac,
                state_changes=changes_woc_vac,
                state_change_description=desc_woc_vac,
                self_rating=eval_woc_vac.self_rating,
                self_reason=eval_woc_vac.self_reason,
            ),
            interaction_woc_var=InteractionResult(
                command=cmd_without,
                va_response=res_woc_var,
                state_changes=changes_woc_var,
                state_change_description=desc_woc_var,
                self_rating=eval_woc_var.self_rating,
                self_reason=eval_woc_var.self_reason,
            ),
        )

        return log.dict()

    def _generate_action_context(self, time: str, hourly_activity: str, member, mem_context: str) -> ActionContext:
        system_role = "당신은 한국어로 시뮬레이션 데이터를 생성합니다. 반드시 JSON만 출력하세요."
        
        family_members_str = ", ".join([f"{m.name}({m.role}, {m.age}세)" for m in self.family.members])
        available_rooms = ", ".join(list(self.environment.rooms.keys()))
        
        prompt_template = Path("prompts/action_context.txt").read_text(encoding="utf-8")
        prompt = prompt_template.format(
            family_members_str=family_members_str,
            time=time,
            hourly_activity=hourly_activity,
            name=member.name,
            role=member.role,
            age=member.age,
            bio=member.bio,
            mem_context=mem_context,
            available_rooms=available_rooms
        )

        try:
            data = query_llm(
                prompt,
                system_role,
                model_schema=ActionContext,
                model=self.model_seq,
                max_retries=1,
                request_timeout=25.0,
            )
            return ActionContext.parse_obj(data)
        except (LLMError, Exception) as exc:  # noqa: BLE001 - fallback for pilot stability
            logger.warning("Action context fallback used at %s (%s): %s", time, member.name, exc)
            return _build_fallback_action_context(hourly_activity)

    def _generate_woc_command(self, wc_command: str, concrete_action: str) -> str:
        system_role = "당신은 한국어로 스마트홈 명령을 변환합니다. 반드시 JSON만 출력하세요."
        prompt_template = Path("prompts/generate_command.txt").read_text(encoding="utf-8")
        prompt = prompt_template.format(
            concrete_action=concrete_action,
            wc_command=wc_command
        )

        try:
            data = query_llm(
                prompt,
                system_role,
                model_schema=CommandOutput,
                model=self.model_seq,
                max_retries=1,
                request_timeout=20.0,
            )
            return CommandOutput.parse_obj(data).command
        except (LLMError, Exception) as exc:  # noqa: BLE001 - fallback for pilot stability
            logger.warning("WOC Command fallback used for WC command '%s': %s", wc_command, exc)
            if wc_command:
                return wc_command
            return "거실 메인 조명 켜줘"

    def _self_evaluate(self, seed_command: str, command: str, response: str, state_changes: List[StateChange], mem_context: str) -> SelfEvaluation:
        system_role = "당신은 사용자 입장에서 만족도를 평가합니다. 반드시 JSON만 출력하세요."
        change_text = _format_state_changes(state_changes)
        prompt_template = Path("prompts/self_evaluate.txt").read_text(encoding="utf-8")
        prompt = prompt_template.format(
            seed_command=seed_command,
            change_text=change_text,
            command=command,
            response=response,
            mem_context=mem_context
        )

        try:
            data = query_llm(
                prompt,
                system_role,
                model_schema=SelfEvaluation,
                model=self.model_seq,
                max_retries=1,
                request_timeout=20.0,
            )
            return SelfEvaluation.parse_obj(data)
        except (LLMError, Exception) as exc:  # noqa: BLE001 - fallback for pilot stability
            logger.warning("Self-evaluation fallback used for command '%s': %s", command, exc)
            if state_changes:
                return SelfEvaluation(self_rating=6, self_reason="기기 상태 변화가 발생해 의도 일부 이상이 반영되었습니다.")
            return SelfEvaluation(self_rating=3, self_reason="기기 상태 변화가 없어 의도 반영이 제한적이었습니다.")

    def _load_existing_logs(self) -> List[Dict[str, Any]]:
        if self.log_path.exists():
            try:
                raw = _load_json(self.log_path)
                if not isinstance(raw, list):
                    return []

                normalized: List[Dict[str, Any]] = []
                dropped = 0
                for item in raw:
                    parsed = _normalize_existing_log_entry(item)
                    if parsed is None:
                        dropped += 1
                        continue
                    normalized.append(parsed)

                if dropped:
                    logger.warning("Dropped %d incompatible old log entries from %s", dropped, self.log_path)
                return normalized
            except Exception:
                return []
        return []
