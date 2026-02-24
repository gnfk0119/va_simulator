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
from src.va_agent import execute_command
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

    for day in day_range:
        for hour in range(24):
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


def _fallback_latent_command(activity: str) -> str:
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


def _build_fallback_action_context(activity: str) -> ActionContext:
    latent = _fallback_latent_command(activity)
    quarterly = f"{activity} 활동의 일부 진행" if activity else "기본 생활 일부 진행"
    concrete = f"{activity} 활동을 집 안에서 진행 중입니다. 현재 주변을 둘러보며 상태를 살핍니다. 필요한 물건을 찾아 사용하려고 합니다." if activity else "집 안에서 기본 생활을 진행 중입니다. 휴식을 취하거나 주변을 정리합니다. 특별한 행동 변화 없이 시간을 보냅니다."
    return ActionContext(
        quarterly_activity=quarterly,
        concrete_action=concrete,
        latent_command=latent,
        needs_voice_command=bool(latent),
    )


def _normalize_existing_log_entry(entry: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(entry, dict):
        return None

    # Backward compatibility for old field names.
    if "concrete_action" not in entry and "visible_action" in entry:
        entry["concrete_action"] = entry.get("visible_action", "")
    if "latent_command" not in entry and "hidden_context" in entry:
        entry["latent_command"] = entry.get("hidden_context", "")

    try:
        return InteractionLog.parse_obj(entry).dict()
    except Exception:
        return None


class MemorySystem:
    def __init__(self):
        self.memories: List[MemoryItem] = []

    def add_memory(self, time: str, member_id: str, desc: str, shared_with: List[str]):
        self.memories.append(MemoryItem(
            time=time,
            member_id=member_id,
            description=desc,
            decay_weight=1.0,
            shared_with=shared_with
        ))

    def update_decay(self):
        # 1시간 루프 등 특정 시점에 호출되어 모든 메모리의 decay를 줄임
        for m in self.memories:
            m.decay_weight = max(0.3, round(m.decay_weight - 0.05, 2))

    def get_context_for_member(self, member_id: str) -> str:
        my_mems = [m for m in self.memories if member_id in m.shared_with]
        if not my_mems:
            return "관찰되는 다른 가족의 행동이나 최근 상황 없음."
        
        my_mems.sort(key=lambda x: x.decay_weight, reverse=True)
        # 상위 8개 정도 보여주기
        lines = [f" - [{m.time}] {m.description} (기억가중치: {m.decay_weight})" for m in my_mems[:8]]
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
        _save_json(memory_out_path, [m.dict() for m in self.memory.memories])

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
                latent_command="",
                shared_memory_refs=[mem_context],
                interaction_with_context=None,
                interaction_without_context=None
            )
            return log.dict()

        # 1. 15분 단위 구체적 행동(Concrete Action) 및 잠재 명령(Latent Command) 생성
        action_context = self._generate_action_context(time, hourly_activity, member, mem_context)
        
        # 2. 모든 15분 단위 행동은 메모리(상태 관찰 로그)에 무조건 저장
        shared_list = [m.member_id for m in self.family.members]
        mem_desc = f"[{member.name}] {action_context.quarterly_activity}"
        self.memory.add_memory(time, member.member_id, mem_desc, shared_list)

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
                location="집 안",
                hourly_activity=hourly_activity,
                quarterly_activity=action_context.quarterly_activity,
                concrete_action=action_context.concrete_action,
                latent_command="",
                shared_memory_refs=[mem_context],
                interaction_with_context=None,
                interaction_without_context=None
            )
            return log.dict()

        print(f"🗣️ [ACT] {time} {member.name}: {action_context.concrete_action} (잠재: {action_context.latent_command})")

        # 3. 두 종류의 발화 생성 (With Context / Without Context)
        cmd_with = self._generate_command(action_context.latent_command, action_context.concrete_action, include_context=True)
        cmd_without = self._generate_command(action_context.latent_command, action_context.concrete_action, include_context=False)

        # VA 호출 자체도 메모리에 기록
        self.memory.add_memory(time, member.member_id, f"[{member.name}] VA에게 '{cmd_with}'라고 음성 명령함", shared_list)

        # 4. 환경 상태를 보존하며 각각 실행
        env_copy_without = Environment.parse_obj(self.environment.dict())
        res_without, changes_without, desc_without = execute_command(cmd_without, env_copy_without, model=self.model_va)
        
        res_with, changes_with, desc_with = execute_command(cmd_with, self.environment, model=self.model_va)

        # 5. Self Evaluate
        eval_with = self._self_evaluate(action_context.latent_command, cmd_with, res_with, changes_with)
        eval_without = self._self_evaluate(action_context.latent_command, cmd_without, res_without, changes_without)

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
            location="집 안",
            hourly_activity=hourly_activity,
            quarterly_activity=action_context.quarterly_activity,
            concrete_action=action_context.concrete_action,
            latent_command=action_context.latent_command,
            shared_memory_refs=[mem_context],
            interaction_with_context=InteractionResult(
                command=cmd_with,
                va_response=res_with,
                state_changes=changes_with,
                state_change_description=desc_with,
                self_rating=eval_with.self_rating,
                self_reason=eval_with.self_reason
            ),
            interaction_without_context=InteractionResult(
                command=cmd_without,
                va_response=res_without,
                state_changes=changes_without,
                state_change_description=desc_without,
                self_rating=eval_without.self_rating,
                self_reason=eval_without.self_reason
            )
        )

        return log.dict()

    def _generate_action_context(self, time: str, hourly_activity: str, member, mem_context: str) -> ActionContext:
        system_role = "당신은 한국어로 시뮬레이션 데이터를 생성합니다. 반드시 JSON만 출력하세요."
        
        family_members_str = ", ".join([f"{m.name}({m.role}, {m.age}세)" for m in self.family.members])
        
        prompt = f"""
        [가구원 정보 (주의: 이 구성원 외의 인물은 임의로 상상하지 마세요!)]
        우리 가족 구성원: {family_members_str}

        [상황 정보]
        - 시간: {time} (이 시간의 15분 단위 행동을 묘사합니다)
        - 1시간 대분류 활동: "{hourly_activity}"
        - 현재 행동하는 사람: {member.name} ({member.role}, {member.age}세)
        - 인물 소개(Bio): {member.bio}
        
        [현재 집 안의 관찰 가능한 다른 가족들의 상태 (Shared Memory)]
        {mem_context}

        요구 사항:
        1) 'quarterly_activity': 1시간 대분류 활동 안에서, 이 특정 15분 동안 수행하는 구체적인 활동 요약입니다 (예: "아침 식사를 위해 계란 프라이 굽기").
        2) 'concrete_action': 'quarterly_activity'에서 수행하는 행동을 사용자 입장에서 **시퀀스가 있는 구체적인 행동으로 최소 3문장 이상** 작성하세요. (장소 이동, 도구 사용, 기기 동작 등을 포함해 매우 상세히 묘사. 예: 거실에서 주방으로 걸어들어온다. 아침식사를 위해 냉장고에서 계란을 꺼낸다. 가스레인지를 켜고 프라이팬에 계란을 굽는다.)
        3) 'latent_command': 이 행동을 진행하면서 스마트홈 환경(VA)에 실제로 요청하고 싶은 명령어(잠재 명령)를 나타냅니다. 속마음이 아닌 직접적인 명령문 형태여야 합니다 (예: 주방 후드 켜줘).
        4) 'needs_voice_command' (True/False): 이 상황에서 스마트홈 VA(음성 인식 비서, IoT 제어 등)에게 명령을 내릴 확률이 있는지 여부.

        출력 형식:
        {{
          "quarterly_activity": "간단히 요약된 15분 단위 활동명",
          "concrete_action": "첫 번째 행동 문장입니다. 두 번째 이어지는 행동 묘사입니다. 세 번째 구체적인 도구 활용이나 상황 설명 문장입니다.",
          "latent_command": "필요한 기기 제어 명령어",
          "needs_voice_command": true
        }}
        """.strip()

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

    def _generate_command(self, latent_command: str, concrete_action: str, include_context: bool) -> str:
        system_role = "당신은 한국어로 스마트홈 명령을 생성합니다. 반드시 JSON만 출력하세요."
        
        condition = f"잠재 명령: {latent_command}" if include_context else "상황 설명 없이, 잠재 명령의 핵심 기기 제어 요구만 짧게 재생성"

        prompt = f"""
        [상황]
        - 현재 행동: {concrete_action}
        - 참고 사항: {condition}

        스마트홈 VA에게 할 자연스러운 한국어 명령을 만들어 주세요.
        명령 생성 시 {'자신의 상황이나 이유를 구체적으로 포함하여 말하세요' if include_context else '상황 설명 없이 오직 기기 제어나 명령 내용만 짧게 말하세요'}.

        출력 형식:
        {{
          "command": "거실 에어컨 켜줘"
        }}
        """.strip()

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
            logger.warning("Command fallback used for latent command '%s': %s", latent_command, exc)
            if latent_command:
                return latent_command
            return "거실 메인 조명 켜줘"

    def _self_evaluate(self, latent_command: str, command: str, response: str, state_changes: List[StateChange]) -> SelfEvaluation:
        system_role = "당신은 사용자 입장에서 만족도를 평가합니다. 반드시 JSON만 출력하세요."
        change_text = _format_state_changes(state_changes)
        prompt = f"""
        [상황] 사용자의 목적(잠재 명령): {latent_command}
        [결과] 기기 변화: {change_text}
        [대화] 나: "{command}" / VA: "{response}"

        위 상황을 종합할 때, 스마트홈의 대응이 본인의 진짜 의도(잠재 명령)를 얼마나 잘 충족했습니까? (1-7점)
        출력 형식:
        {{
          "self_rating": 7,
          "self_reason": "이유"
        }}
        """.strip()

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
