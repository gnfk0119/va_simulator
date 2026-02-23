import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

from pydantic import BaseModel

from src.schema import (
    FamilyProfile, Environment, InteractionLog, StateChange, 
    ActionContext, InteractionResult, MemoryItem
)
from src.va_agent import execute_command
from utils.llm_client import query_llm
from utils.logger import get_logger

logger = get_logger(__name__)

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
        model: Optional[str] = None,
    ) -> None:
        self.environment_path = environment_path
        self.family_path = family_path
        self.log_path = log_path
        self.model = model

        env_data = _load_json(environment_path)
        family_data = _load_json(family_path)

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
                        "activity": event.activity,
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
                # 외출 중이면 시뮬레이션 생략
                continue
                
            log_entry = self.run_step(step)
            if log_entry:
                logs.append(log_entry)
                _save_json(self.log_path, logs)

        # 메모리 기록도 별도 저장
        memory_out_path = self.log_path.parent / "memory_history.json"
        _save_json(memory_out_path, [m.dict() for m in self.memory.memories])

        return logs

    def run_step(self, step: dict) -> Optional[Dict[str, Any]]:
        time = step["time"]
        activity = step["activity"]
        member = step["member"]
        
        # 메모리 불러오기
        mem_context = self.memory.get_context_for_member(member.member_id)

        # 1. 15분 단위 구체적 행동(Concrete Action) 및 잠재 명령(Latent Command) 생성
        action_context = self._generate_action_context(time, activity, member, mem_context)
        
        # 2. 모든 15분 단위 행동은 메모리(상태 관찰 로그)에 무조건 저장
        shared_list = [m.member_id for m in self.family.members]
        mem_desc = f"[{member.name}] {action_context.concrete_action}"
        self.memory.add_memory(time, member.member_id, mem_desc, shared_list)

        if not action_context.needs_voice_command:
            print(f"⏭️ [SKIP] {time} {member.name}: {action_context.concrete_action}")
            return None

        print(f"🗣️ [ACT] {time} {member.name}: {action_context.concrete_action} (잠재: {action_context.latent_command})")

        # 3. 두 종류의 발화 생성 (With Context / Without Context)
        cmd_with = self._generate_command(action_context.latent_command, action_context.concrete_action, include_context=True)
        cmd_without = self._generate_command(action_context.latent_command, action_context.concrete_action, include_context=False)

        # VA 호출 자체도 메모리에 기록
        self.memory.add_memory(time, member.member_id, f"[{member.name}] VA에게 '{cmd_with}'라고 음성 명령함", shared_list)

        # 4. 환경 상태를 보존하며 각각 실행
        env_copy_without = Environment.parse_obj(self.environment.dict())
        res_without, changes_without, desc_without = execute_command(cmd_without, env_copy_without)
        
        res_with, changes_with, desc_with = execute_command(cmd_with, self.environment)

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

    def _generate_action_context(self, time: str, activity: str, member, mem_context: str) -> ActionContext:
        system_role = "당신은 한국어로 시뮬레이션 데이터를 생성합니다. 반드시 JSON만 출력하세요."
        
        family_members_str = ", ".join([f"{m.name}({m.role}, {m.age}세)" for m in self.family.members])
        
        prompt = f"""
        [가구원 정보 (주의: 이 구성원 외의 인물은 임의로 상상하지 마세요!)]
        우리 가족 구성원: {family_members_str}

        [상황 정보]
        - 시간: {time}
        - 1시간 대분류 활동: "{activity}"
        - 현재 행동하는 사람: {member.name} ({member.role}, {member.age}세, {member.traits})
        
        [현재 집 안의 관찰 가능한 다른 가족들의 상태 (Shared Memory)]
        {mem_context}

        요구 사항:
        1) 'concrete_action'은 이 사람이 현재 15분 동안 어떤 구체적인 행동을 하는지 묘사합니다 (집 안 위치 포함).
        2) 'latent_command'는 이 행동 중 VA에게 하고 싶은 실제 명령어(잠재 명령)를 나타냅니다. 속마음이 아닌 직접적인 명령문 형태여야 합니다.
        3) 'needs_voice_command' (True/False): 이 상황에서 스마트홈 VA(음성 인식 비서, IoT 제어 등)에게 명령을 내릴 확률이 있는지 여부.

        출력 형식:
        {{
          "concrete_action": "거실 소파에 앉아 조용히 휴식 중",
          "latent_command": "더우니까 거실 에어컨 좀 켜줘",
          "needs_voice_command": true
        }}
        """.strip()

        data = query_llm(prompt, system_role, model_schema=ActionContext, model=self.model)
        return ActionContext.parse_obj(data)

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

        data = query_llm(prompt, system_role, model_schema=CommandOutput, model=self.model)
        return CommandOutput.parse_obj(data).command

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

        data = query_llm(prompt, system_role, model_schema=SelfEvaluation, model=self.model)
        return SelfEvaluation.parse_obj(data)

    def _load_existing_logs(self) -> List[Dict[str, Any]]:
        if self.log_path.exists():
            try:
                return _load_json(self.log_path)
            except Exception:
                return []
        return []