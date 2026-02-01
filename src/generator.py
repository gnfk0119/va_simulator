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
    system_role = (
        "당신은 스마트홈 연구용 데이터를 생성하는 도우미입니다. "
        "모든 묘사와 대사는 한국어로 출력하세요. 반드시 JSON만 출력하세요."
    )
    prompt = """
      한국의 일반적인 30평대 아파트(거실, 주방, 안방, 작은방, 욕실, 다용도실) 구조와 스마트홈 IoT 기기 구성을 JSON으로 작성하세요.

      [1. 필수 인프라 (모든 방 공통)]
      - 각 방에는 반드시 '메인 조명(Ceiling Light)'과 '스위치'가 포함되어야 합니다. (is_observable: true)

      [2. 필수 가전 (반드시 포함)]
      - 아래 기기들은 한국 가정의 필수품이므로 지정된 위치에 반드시 배치하세요.
        - 거실: 스탠드형 에어컨, 스마트 TV, 로봇청소기, 월패드(Wall-pad)
        - 주방: 냉장고, 김치냉장고, 전자레인지, 식기세척기, 주방 후드
        - 다용도실: 세탁기, 건조기

      [3. 선택 가전 및 소품 (상황에 따라 5~10개 랜덤 추가)]
      - 아래의 [선택지 풀]에서 기기를 골라, 방의 용도에 어울리게 적절히 분배하여 추가하세요. (모두 다 넣을 필요 없음)
      - **선택지 풀:**
        - 생활 가전: 공기청정기, 제습기, 에어드레서(스타일러), 선풍기
        - 조명/분위기: 스마트 블라인드/커튼, 무드등, 플로어 스탠드 조명, LED 스트립
        - 센서류: 문 열림 센서, 모션 센서, 온습도 센서, 스마트 플러그, 가스 밸브 차단기

      [4. 데이터 구조 제약]
      1. 결과는 반드시 JSON만 출력합니다.
      2. 각 기기 속성에는 `state_value`와 `is_observable`을 포함합니다.
      3. `is_observable` 설정 기준:
        - True (관측 가능): 전등 켜짐, 블라인드 내려감, TV 화면, 공기청정기 디스플레이 숫자
        - False (관측 불가): 스마트 플러그 내부 전력량, 보이지 않는 센서의 통신 상태, 매립형 배관 상태

      [JSON 스키마 예시]
      {
        "rooms": {
          "거실": [
            {
              "name": "거실 메인 조명",
              "properties": {
                "power": {"state_value": "on", "is_observable": true},
                "brightness": {"state_value": "100", "is_observable": true}
              }
            },
            {
              "name": "스마트 블라인드",
              "properties": {
                "position": {"state_value": "50%", "is_observable": true}
              }
            }
          ]
        }
      }
      """.strip()

    data = query_llm(prompt, system_role, model_schema=Environment, model=model)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info("Environment generated at %s", output_path)
    return data


def generate_avatar(
    output_path: Path,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    system_role = (
        "당신은 연구용 페르소나와 스케줄을 만드는 도우미입니다. "
        "모든 묘사와 대사는 한국어로 출력하세요. 반드시 JSON만 출력하세요."
    )
    prompt = """
      한국에 거주하는 1인 가구 페르소나를 만들고, **주말 하루(1 Day) 동안의 상세 활동 스케줄**을 JSON으로 작성하세요.

      요구 사항:
      1. 결과는 반드시 JSON만 출력합니다.
      2. **스케줄은 단 하루(1 Day)의 일과이며, 기상부터 취침까지 최소 20개 이상의 활동(Steps)으로 구성되어야 합니다.**
      3. 시간 간격은 10분~30분 단위로 촘촘하게 작성하세요.
      4. 각 활동은 스마트홈 기기(조명, TV, 에어컨, 로봇청소기, 블라인드 등)와 **상호작용할 가능성이 높은 활동** 위주로 구성하세요.
        - 좋은 예: "소파에서 넷플릭스 보기", "침대에서 독서하며 스탠드 조명 켜기", "요리 중 환기시키기"
        - 나쁜 예: "외출 중", "카페에서 독서" (집 밖 활동 최소화)
      5. 시간 형식은 "HH:MM" (24시간제)로 작성하세요.

      스키마:
      {
        "name": "이름",
        "traits": "성격/직업/라이프스타일 묘사 (기기 사용 성향 포함)",
        "schedule": [
          {"time": "08:00", "activity": "기상 및 침실 조명 켜기"},
          {"time": "08:10", "activity": "화장실로 이동하여 세수"},
          ...
        ]
      }
      """.strip()

    # data = query_llm(prompt, system_role, model_schema=AvatarProfile, model=model)
    # output_path.parent.mkdir(parents=True, exist_ok=True)
    # with output_path.open("w", encoding="utf-8") as f:
    #     json.dump(data, f, ensure_ascii=False, indent=2)

    # logger.info("Avatar profile generated at %s", output_path)
    # return data

    data = query_llm(prompt, system_role, model_schema=AvatarProfile, model=model)
    
    # 폴더가 없으면 생성
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info("Avatar profile generated at %s", output_path)
    return data