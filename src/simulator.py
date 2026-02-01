from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from src.schema import AvatarProfile, Environment, InteractionLog, StateChange
from src.va_agent import execute_command
from utils.llm_client import query_llm
from utils.logger import get_logger


logger = get_logger(__name__)


# [수정 1] needs_voice_command 필드 추가
class ActionContext(BaseModel):
    visible_action: str
    hidden_context: str
    needs_voice_command: bool  # 발화 필요 여부를 LLM이 판단


class CommandOutput(BaseModel):
    command: str


class SelfEvaluation(BaseModel):
    self_rating: int
    self_reason: str


# [수정 2] 하드코딩된 키워드 리스트 및 _is_speakable 함수 삭제
# SPEECH_BLOCK_KEYWORDS = [...]  <-- 삭제됨
# def _is_speakable(...) <-- 삭제됨


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
    parts = [
        f"{c.device_name}.{c.property_name}: {c.before} -> {c.after}" for c in changes
    ]
    return "; ".join(parts)


class SimulationEngine:
    def __init__(
        self,
        environment_path: Path = Path("data/generated/environment.json"),
        avatar_path: Path = Path("data/generated/avatar_profile.json"),
        log_path: Path = Path("data/logs/simulation_log_full.json"),
        model: Optional[str] = None,
    ) -> None:
        self.environment_path = environment_path
        self.avatar_path = avatar_path
        self.log_path = log_path
        self.model = model

        env_data = _load_json(environment_path)
        avatar_data = _load_json(avatar_path)

        self.environment = Environment.parse_obj(env_data)
        self.avatar = AvatarProfile.parse_obj(avatar_data)

    def run(self) -> List[Dict[str, Any]]:
        logs = self._load_existing_logs()
        for event in self.avatar.schedule:
            log_entry = self.run_step(event.time, event.activity)
            if log_entry:
                logs.append(log_entry)
                _save_json(self.log_path, logs)
        return logs

    def run_step(self, time: str, activity: str) -> Optional[Dict[str, Any]]:
        action_context = self._generate_action_context(time, activity)
        
        # [수정 3] LLM의 판단(needs_voice_command)에 따라 스킵 여부 결정
        if not action_context.needs_voice_command:
            logger.info("Skip step at %s (No voice command needed)", time)
            return None

        command = self._generate_command(action_context.hidden_context, action_context.visible_action)
        response, state_changes = execute_command(command, self.environment)

        evaluation = self._self_evaluate(
            action_context.hidden_context,
            command,
            response,
            state_changes,
        )

        log = InteractionLog(
            time=time,
            visible_action=action_context.visible_action,
            hidden_context=action_context.hidden_context,
            command=command,
            va_response=response,
            state_changes=state_changes,
            self_rating=evaluation.self_rating,
            self_reason=evaluation.self_reason,
        )

        return log.dict()

    def _generate_action_context(self, time: str, activity: str) -> ActionContext:
        system_role = "당신은 한국어로 시뮬레이션 데이터를 생성합니다. 반드시 JSON만 출력하세요."
        # [수정 4] needs_voice_command 판단 기준을 프롬프트에 추가
        prompt = f"""
            현재 시간은 {time}, 활동은 "{activity}"입니다.

            요구 사항:
            1) 겉보기 행동(visible_action)은 관찰 가능한 묘사만 합니다. 의도는 드러내지 않습니다.
            2) 속마음(hidden_context)은 구체적인 제약/불편/의도를 포함합니다.
            3) needs_voice_command는 현재 상황에서 스마트홈 VA에게 명령을 내리거나 정보를 물어볼 필요가 있는지를 True/False로 판단합니다.
            - 예: "양치 중이라 말하기 힘들다" -> false
            - 예: "소파에 앉아 TV를 켜고 싶다" -> true
            4) 반드시 JSON만 출력합니다.

            출력 형식:
            {{
            "visible_action": "...",
            "hidden_context": "...",
            "needs_voice_command": true
            }}
            """.strip()

        data = query_llm(prompt, system_role, model_schema=ActionContext, model=self.model)
        return ActionContext.parse_obj(data)

    def _generate_command(self, hidden_context: str, visible_action: str) -> str:
        system_role = "당신은 한국어로 스마트홈 명령을 생성합니다. 반드시 JSON만 출력하세요."
        # [수정 5] 목적 지향적(Goal-oriented) 명령 우선 생성 지침 추가
        prompt = f"""
            [상황]
            - 속마음: {hidden_context}
            - 겉보기 행동: {visible_action}

            위 상황을 해결하거나 돕기 위해 스마트홈 VA에게 할 자연스러운 한국어 명령을 만들어 주세요.

            지침:
            1) 단순 잡담(Chit-chat)보다는 **IoT 기기 제어(조명, 온도, 가전 등)나 정보 확인(날씨, 시간, 일정)**과 같은 목적 지향적(Goal-oriented) 명령을 우선적으로 생성하세요.
            2) 반드시 JSON만 출력하세요.

            출력 형식:
            {{
            "command": "..."
            }}
            """.strip()

        data = query_llm(prompt, system_role, model_schema=CommandOutput, model=self.model)
        return CommandOutput.parse_obj(data).command

    def _self_evaluate(
        self,
        hidden_context: str,
        command: str,
        response: str,
        state_changes: List[StateChange],
    ) -> SelfEvaluation:
        system_role = "당신은 사용자 입장에서 만족도를 평가합니다. 반드시 JSON만 출력하세요."
        change_text = _format_state_changes(state_changes)
        prompt = f"""
            [상황] 속마음: {hidden_context}
            [결과] 기기 변화: {change_text}
            [대화] 나: "{command}" / VA: "{response}"

            위 정보를 종합할 때, 본인의 의도가 얼마나 잘 충족되었습니까? (1-7점)
            반드시 JSON만 출력하세요.

            출력 형식:
            {{
            "self_rating": 1,
            "self_reason": "이유"
            }}
            """.strip()

        data = query_llm(prompt, system_role, model_schema=SelfEvaluation, model=self.model)
        return SelfEvaluation.parse_obj(data)

    def _load_existing_logs(self) -> List[Dict[str, Any]]:
        if self.log_path.exists():
            return _load_json(self.log_path)
        return []