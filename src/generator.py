from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any, Optional

from src.schema import AvatarProfile, Environment
from utils.llm_client import query_llm
from utils.logger import get_logger


logger = get_logger(__name__)


def generate_environment(
    output_path: Path = Path("data/generated/environment.json"),
    model: Optional[str] = None,
) -> Dict[str, Any]:
    system_role = "당신은 스마트홈 연구용 데이터를 생성하는 도우미입니다. 반드시 JSON만 출력하세요."
    prompt = """
한국의 일반적인 30평대 아파트 구조와 스마트홈 IoT 기기 구성을 JSON으로 작성하세요.

요구 사항:
1) 결과는 반드시 JSON만 출력합니다.
2) 구조는 아래 스키마를 따릅니다.
3) 각 기기 속성에는 state_value와 is_observable을 포함합니다.
4) is_observable은 '제 3자가 눈으로 상태를 확인 가능한지'를 True/False로 설정합니다.
5) 방 이름과 기기 이름은 한국어로 작성하세요.

스키마:
{
  "rooms": {
    "거실": [
      {
        "name": "거실 조명",
        "properties": {
          "power": {"state_value": "off", "is_observable": true},
          "brightness": {"state_value": "50%", "is_observable": true}
        }
      }
    ]
  }
}

힌트:
- 관측 가능 예시: 전등, TV 전원, 블라인드 위치
- 관측 불가 예시: 스마트 플러그의 내부 전류량, 네트워크 지연
""".strip()

    data = query_llm(prompt, system_role, model_schema=Environment, model=model)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info("Environment generated at %s", output_path)
    return data


def generate_avatar(
    output_path: Path = Path("data/generated/avatar_profile.json"),
    model: Optional[str] = None,
) -> Dict[str, Any]:
    system_role = "당신은 연구용 페르소나와 스케줄을 만드는 도우미입니다. 반드시 JSON만 출력하세요."
    prompt = """
한국에서 거주하는 1인 가구 페르소나를 만들고 일주일치 스케줄을 JSON으로 작성하세요.

요구 사항:
1) 결과는 반드시 JSON만 출력합니다.
2) 구조는 아래 스키마를 따릅니다.
3) schedule은 7일치이며, 각 항목의 time은 "요일 HH:MM" 형식입니다.
4) activity는 구체적 행동을 간단히 묘사합니다. (예: "퇴근 후 TV 시청")

스키마:
{
  "name": "이름",
  "traits": "성격/직업/라이프스타일 묘사",
  "schedule": [
    {"time": "월요일 07:30", "activity": "아침 준비"}
  ]
}
""".strip()

    data = query_llm(prompt, system_role, model_schema=AvatarProfile, model=model)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info("Avatar profile generated at %s", output_path)
    return data
