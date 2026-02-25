from __future__ import annotations

import json
from pathlib import Path
from typing import List, Tuple, Any

from pydantic import BaseModel, Field
from src.schema import Environment, StateChange
from utils.llm_client import query_llm
from utils.logger import get_logger

logger = get_logger(__name__)

# LLM이 출력할 응답 구조 정의
class VAResponse(BaseModel):
    response_text: str = Field(..., description="사용자에게 할 자연스러운 한국어 응답")
    changes: List[StateChange] = Field(default_factory=list, description="기기 상태 변경 내역 리스트")
    state_change_description: str = Field(..., description="기기들이 어떻게 조작되었는지 하나의 자연스러운 한국어 문장으로 요약 (예: 거실 에어컨이 켜지고 온도가 18도로 설정되었습니다.) 상태 변경이 없으면 빈 문자열.")

def execute_command(
    command: str, 
    environment: Environment, 
    model: str = "gpt-4o"
) -> Tuple[str, List[StateChange], str]:
    """
    LLM을 사용하여 환경(Environment)을 이해하고 명령을 수행합니다.
    """
    
    # Pydantic V2/V1 호환성 처리 (한국어 깨짐 방지)
    try:
        env_dict = environment.model_dump()
        env_state = json.dumps(env_dict, ensure_ascii=False, indent=2)
    except AttributeError:
        env_state = environment.json(ensure_ascii=False)

    # 1. Provide a parsed, strict allow-list of devices and their properties.
    device_allowlist_lines = []
    for room_name, objects in environment.rooms.items():
        device_allowlist_lines.append(f"- {room_name}")
        for obj in objects:
            props = list(obj.properties.keys())
            device_allowlist_lines.append(f"  - {obj.name} {props}")
    device_allowlist_str = "\n".join(device_allowlist_lines)

    system_role = "당신은 스마트홈 AI 비서입니다. 현재 집안의 가용 기기 상태를 보고 사용자의 명령을 수행하세요."
    
    prompt_template = Path("prompts/va_agent.txt").read_text(encoding="utf-8")
    prompt = prompt_template.format(
        device_allowlist_str=device_allowlist_str,
        env_state=env_state,
        command=command
    )

    # 2. LLM 호출
    try:
        # Pydantic 모델 스키마를 넘겨주지만, 프롬프트 예시가 더 강력하게 작용함
        result = query_llm(prompt, system_role, model_schema=VAResponse, model=model)
        parsed_result = VAResponse.parse_obj(result)
    except Exception as e:
        logger.error(f"VA Agent LLM Error: {e}")
        # 에러 발생 시 프로그램이 멈추지 않고, 사용자에게 사과 후 넘어가도록 처리
        return "죄송합니다. 잠시 시스템 오류가 있어 요청을 처리하지 못했어요.", [], "관측 가능한 기기 상태 변화 없음"

    # 3. 실제 Environment 객체 업데이트 (State Update)
    applied_changes = []
    
    for change in parsed_result.changes:
        target_device = None
        # 1차 시도: 해당 기기 정확히 찾기
        for room_name, objects in environment.rooms.items():
            for obj in objects:
                if obj.name == change.device_name:
                    target_device = obj
                    break
            if target_device:
                break
        
        # 2차 시도: LLM이 '침실1(안방) 메인 조명' 같이 방 이름과 섞어서 생성한 경우를 위한 휴리스틱(부분 일치)
        if target_device is None:
            norm_target = change.device_name.replace(" ", "").replace("/", "").replace("(", "").replace(")", "")
            for room_name, objects in environment.rooms.items():
                for obj in objects:
                    norm_obj = obj.name.replace(" ", "").replace("/", "").replace("(", "").replace(")", "")
                    if norm_obj in norm_target or norm_target in norm_obj:
                        target_device = obj
                        change.device_name = obj.name
                        logger.info(f"Fallback matched device '{change.device_name}' via substring matching.")
                        break
                if target_device:
                    break

        if target_device is None:
            logger.warning(f"Failed to apply change: Device '{change.device_name}' not found in environment.")
            continue

        prop_name = change.property_name
        
        # Fallback 1: if LLM hallucinates 'brightness' but target only has 'power', map to 'power' heuristically
        if prop_name not in target_device.properties:
            if prop_name == "brightness" and "power" in target_device.properties:
                prop_name = "power"
                change.after = "on" if str(change.after).strip() != "0" else "off"
                logger.info(f"Fallback matched '{change.device_name}': mapped 'brightness' to 'power' ({change.after})")

        if prop_name in target_device.properties:
            # 상태 업데이트 적용
            target_device.properties[prop_name].state_value = change.after
            
            # 레코드를 위해 프로퍼티 이름도 변경된 값으로 동기화
            change.property_name = prop_name
            applied_changes.append(change)
        else:
            logger.warning(f"Failed to apply change: {change.device_name}.{prop_name} not found.")

    return parsed_result.response_text, applied_changes, parsed_result.state_change_description