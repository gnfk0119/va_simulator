from __future__ import annotations

from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Tuple

from src.schema import Environment, StateChange
from utils.llm_client import query_llm
from utils.logger import get_logger
from src.config import config

logger = get_logger(__name__)

class ClassificationResult(BaseModel):
    domain: str
    intent: str
    device_entity: str
    target_value: str

class VAResponse(BaseModel):
    response_text: str = Field(..., description="사용자에게 전달할 음성 메시지")
    changes: List[StateChange] = Field(default_factory=list, description="기기 상태 변경 내역 리스트")
    state_change_description: str = Field(..., description="기기들이 어떻게 조작되었는지 하나의 자연스러운 한국어 문장으로 요약 (상태 변경이 없으면 빈 문자열)")

_domain_intent_csv_cache: str | None = None
_domain_intent_matrix_cache: str | None = None

def _load_domain_intent_csv() -> str:
    global _domain_intent_csv_cache
    if _domain_intent_csv_cache is None:
        try:
            _domain_intent_csv_cache = Path("data/domain_intent_labels_defs.csv").read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to load domain_intent CSV: {e}")
            _domain_intent_csv_cache = "domain,intent,description\nnone,none,해당 없음"
    return _domain_intent_csv_cache

def _load_domain_intent_matrix() -> str:
    global _domain_intent_matrix_cache
    if _domain_intent_matrix_cache is None:
        try:
            _domain_intent_matrix_cache = Path("data/Domain_Intent_metrix.csv").read_text(encoding="utf-8-sig")
        except Exception as e:
            logger.error(f"Failed to load Domain_Intent_metrix.csv: {e}")
            _domain_intent_matrix_cache = "Domain,Intent\n"
    return _domain_intent_matrix_cache

def execute_command(
    command: str,
    environment: Environment,
    model_classifier: str = "gemini-2.5-flash",
    model_response: str = "gpt-4o-mini"
) -> Tuple[str, List[StateChange], str]:
    """
    LLM Classifier를 거쳐 사전에 정의된 규칙(Rule) 기반으로 응답 템플릿을 고정하되,
    상태 변화의 자연스러운 추적(State Change)은 LLM에게 위임하여 VA_C와 통일시킵니다.
    """
    
    # 1. 환경 기기 리스트 취합
    env_devices = []
    device_allowlist_lines = []
    for room_name, objects in environment.rooms.items():
        device_allowlist_lines.append(f"- {room_name}")
        for obj in objects:
            env_devices.append(f"[{room_name}] {obj.name}")
            props = list(obj.properties.keys())
            device_allowlist_lines.append(f"  - {obj.name} {props}")
            
    devices_str = ", ".join(env_devices) if env_devices else "기기 없음"
    device_allowlist_str = "\n".join(device_allowlist_lines)

    # Pydantic V2/V1 호환성 처리 (한국어 깨짐 방지)
    try:
        env_dict = environment.model_dump()
        import json
        env_state = json.dumps(env_dict, ensure_ascii=False, indent=2)
    except AttributeError:
        env_state = environment.json(ensure_ascii=False)

    # 2. NLU (Classifier)
    sys_role_classifier = "당신은 스마트홈 자유발화에서 도메인과 인텐트, 엔티티를 추출하는 NLU 분류기입니다."
    classifier_prompt = Path("prompts/va_r_classifier.txt").read_text(encoding="utf-8").format(
        domain_intent_csv=_load_domain_intent_csv(),
        valid_combos_csv=_load_domain_intent_matrix(),
        command=command,
        environment_devices=devices_str
    )
    
    if isinstance(model_classifier, dict):
        mc = model_classifier
    else:
        mc = config.get("models", {}).get("va_r_classifier", {"provider": "gemini", "model": "gemini-2.5-flash"})
        
    try:
        class_res_dict = query_llm(classifier_prompt, sys_role_classifier, model_schema=ClassificationResult, model=mc)
        class_res = ClassificationResult.parse_obj(class_res_dict)
    except Exception as e:
        logger.error(f"VA_R Classifier Error: {e}")
        return "죄송합니다. 오류가 발생하여 다시 말씀해 주시겠어요?", [], "관측 가능한 기기 상태 변화 없음"
        
    domain = class_res.domain
    intent = class_res.intent
    device_entity = class_res.device_entity
    target_value = class_res.target_value
    
    # 3. NLG & State Change Evaluation
    applied_changes = []
    response_text = ""
    state_desc = "관측 가능한 기기 상태 변화 없음"
    
    from src.va_r_prompts import VA_R_RESPONSE_PROMPTS
    combo_key = f"{domain}_{intent}"
    
    if domain == "none" or intent == "none":
        # 완전 실패시
        response_text = "죄송합니다. 원하시는 의도를 파악하기 어렵거나 현재 지원하지 않는 기능입니다."
    else:
        dynamic_guideline = VA_R_RESPONSE_PROMPTS.get(combo_key, "정해진 가이드라인이 없습니다. 결과에 기반해 간결하게 사실만 응답하세요.")

        sys_role_response = "당신은 스마트홈의 친절한 음성 비서 역할로서 시스템 응답과 기기 상태 변화 내역을 생성합니다."
        response_prompt = Path("prompts/va_r_response.txt").read_text(encoding="utf-8").format(
            domain=domain,
            intent=intent,
            device_entity=device_entity,
            target_value=target_value,
            device_allowlist_str=device_allowlist_str,
            env_state=env_state,
            dynamic_guideline=dynamic_guideline,
            command=command
        )
        
        if isinstance(model_response, dict):
            mr = model_response
        else:
            mr = config.get("models", {}).get("va_r_response", {"provider": "openai", "model": "gpt-4o-mini"})

        try:
            resp_dict = query_llm(response_prompt, sys_role_response, model_schema=VAResponse, model=mr)
            parsed_result = VAResponse.parse_obj(resp_dict)
            response_text = parsed_result.response_text
            state_desc = parsed_result.state_change_description
            
            # Apply Changes back to environment
            for change in parsed_result.changes:
                target_device = None
                norm_target = change.device_name.replace(" ", "").replace("/", "").replace("(", "").replace(")", "")
                for room_name, objects in environment.rooms.items():
                    for obj in objects:
                        norm_obj = obj.name.replace(" ", "").replace("/", "").replace("(", "").replace(")", "")
                        if norm_obj in norm_target or norm_target in norm_obj:
                            target_device = obj
                            change.device_name = obj.name
                            break
                    if target_device:
                        break

                if target_device is None:
                    continue

                prop_name = change.property_name
                # Fallback safeguard if LLM tries to change unsupported property
                if prop_name not in target_device.properties:
                    if prop_name == "brightness" and "power" in target_device.properties:
                        prop_name = "power"
                        change.after = "on" if str(change.after).strip() != "0" else "off"

                if prop_name in target_device.properties:
                    target_device.properties[prop_name].state_value = change.after
                    change.property_name = prop_name
                    applied_changes.append(change)

        except Exception as e:
            logger.error(f"VA_R NLG Error: {e}")
            response_text = "네, 명령수행 중 오류가 발생했습니다."

    if not state_desc and applied_changes:
        state_desc = "; ".join([f"{c.device_name}.{c.property_name}: {c.before} -> {c.after}" for c in applied_changes])
    if not state_desc:
        state_desc = "관측 가능한 기기 상태 변화 없음"
        
    return response_text, applied_changes, state_desc
