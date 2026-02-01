from __future__ import annotations

import json
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

def execute_command(
    command: str, 
    environment: Environment, 
    model: str = "gpt-4o"
) -> Tuple[str, List[StateChange]]:
    """
    LLM을 사용하여 환경(Environment)을 이해하고 명령을 수행합니다.
    """
    
    # Pydantic V2/V1 호환성 처리 (한국어 깨짐 방지)
    try:
        env_dict = environment.model_dump()
        env_state = json.dumps(env_dict, ensure_ascii=False, indent=2)
    except AttributeError:
        env_state = environment.json(ensure_ascii=False)

    system_role = "당신은 스마트홈 AI 비서입니다. 현재 집안의 기기 상태를 보고 사용자의 명령을 수행하세요."
    
    # [핵심 수정] JSON 출력 예시를 프롬프트에 명시적으로 추가
    prompt = f"""
    [현재 집안 환경 및 기기 상태]
    {env_state}

    [사용자 명령]
    "{command}"

    [지시사항]
    1. 사용자의 명령을 해석하여 적절한 기기를 찾고 상태를 변경하세요.
    2. 명령이 모호하면 되묻거나, 가장 적절한 기기를 추론하여 실행하세요.
    3. 실행할 수 없는 명령이면 정중히 거절하세요.
    4. **중요:** 상태 변경 시 `device_name`과 `property_name`은 위 [현재 집안 환경]에 있는 정확한 값을 써야 합니다.
    5. 응답(response_text)은 한국어로 친절하고 자연스럽게 작성하세요.

    [출력 포맷 예시]
    반드시 아래와 같은 JSON 구조로만 출력하세요. (Markdown 코드 블록 없이 순수 JSON만 출력)
    
    {{
      "response_text": "네, 거실 조명을 켰습니다.",
      "changes": [
        {{
          "device_name": "거실 조명",
          "property_name": "power",
          "before": "off",
          "after": "on"
        }}
      ]
    }}

    만약 상태 변경이 없다면 "changes": [] 로 비워두세요.
    """

    # 2. LLM 호출
    try:
        # Pydantic 모델 스키마를 넘겨주지만, 프롬프트 예시가 더 강력하게 작용함
        result = query_llm(prompt, system_role, model_schema=VAResponse, model=model)
        parsed_result = VAResponse.parse_obj(result)
    except Exception as e:
        logger.error(f"VA Agent LLM Error: {e}")
        # 에러 발생 시 프로그램이 멈추지 않고, 사용자에게 사과 후 넘어가도록 처리
        return "죄송합니다. 잠시 시스템 오류가 있어 요청을 처리하지 못했어요.", []

    # 3. 실제 Environment 객체 업데이트 (State Update)
    applied_changes = []
    
    for change in parsed_result.changes:
        target_device = None
        # 해당 기기 찾기
        for room_name, objects in environment.rooms.items():
            for obj in objects:
                if obj.name == change.device_name:
                    target_device = obj
                    break
            if target_device:
                break
        
        if target_device and change.property_name in target_device.properties:
            # 상태 업데이트 적용
            target_device.properties[change.property_name].state_value = change.after
            applied_changes.append(change)
        else:
            logger.warning(f"Failed to apply change: {change.device_name}.{change.property_name} not found.")

    return parsed_result.response_text, applied_changes