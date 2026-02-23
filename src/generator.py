import json
import random
import pandas as pd
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

from src.schema import FamilyProfile, Environment, MemberProfile, ScheduleEvent
from utils.llm_client import query_llm
from utils.logger import get_logger

logger = get_logger(__name__)

# --- 평면도 타입 (PDF 기준 A, B, C, D) ---
LAYOUT_TYPES = [
    "A (3Bay 전후면, 안방/침실2 전면, 침실3 후면)",
    "B (3Bay 전면형, 거실/침실 3개 전면)",
    "C (2Bay 타워형, 거실/안방 전면, 좁은 복도)",
    "D (4Bay, 거실/침실 3개 전면 일렬 배열)"
]

def generate_environment(
    output_path: Path,
    model: Optional[str] = None,
    theme_hint: str = ""
) -> Dict[str, Any]:
    system_role = "당신은 스마트홈 연구용 데이터를 생성하는 도우미입니다. 모든 묘사와 대사는 한국어로 출력하세요. 반드시 JSON만 출력하세요."
    picked_layout = random.choice(LAYOUT_TYPES)
    balcony_mode = random.choice(["standard", "expanded"])
    
    prompt = f"""
    한국의 일반적인 30평대 아파트 구조와 스마트홈 IoT 기기 구성을 JSON으로 작성하세요.

    [테마 및 레이아웃]
    - 평면도 타입: {picked_layout}
    - 발코니 모드: {balcony_mode}
    - 추가 테마 힌트: {theme_hint}

    [1. 필수 인프라 (모든 방 공통)]
    - 각 방에는 반드시 '메인 조명(Ceiling Light)'과 '스위치'가 포함되어야 합니다. (is_observable: true)

    [2. 필수 가전 (반드시 포함)]
    - 거실: 스탠드형 에어컨, 스마트 TV, 로봇청소기, 월패드(Wall-pad)
    - 주방/식당: 냉장고, 김치냉장고, 전자레인지, 식기세척기, 주방 후드
    - 방(침실1,2,3): 방 용도에 맞는 가전
    - 다용도실/서비스존: 세탁기, 건조기

    [3. 선택 가전 및 소품 (상황에 따라 5~10개 분배)]
    - 공기청정기, 제습기, 에어드레서(스타일러), 선풍기, 무드등, 스마트 블라인드/커튼, 모션 센서, 스마트 플러그 등

    [4. 데이터 구조 제약]
    1. 반드시 JSON만 출력합니다.
    2. 각 기기 속성에는 `state_value`와 `is_observable`(true/false)을 포함합니다.
    3. JSON 루트에 `type_name` ("{picked_layout}")과 `balcony_mode` ("{balcony_mode}") 필드 포함!
    4. rooms 안에 방들의 기기 리스트를 작성.

    [JSON 스키마 예시]
    {{
      "type_name": "{picked_layout}",
      "balcony_mode": "{balcony_mode}",
      "rooms": {{
        "거실": [
          {{
            "name": "거실 메인 조명",
            "properties": {{
              "power": {{"state_value": "on", "is_observable": true}},
              "brightness": {{"state_value": "100", "is_observable": true}}
            }}
          }}
        ]
      }}
    }}
    """.strip()

    data = query_llm(prompt, system_role, model_schema=Environment, model=model)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info("Environment generated at %s", output_path)
    return data


# --- 패밀리 및 스케줄 생성 로직 ---
def load_survey_data(survey_path: str = "생활시간조사.xlsx") -> pd.DataFrame:
    df = pd.read_excel(survey_path, sheet_name=0)
    cols_to_ffill = ['성별코드', '연령분류', '결혼여부', '부모자식여부', '경제활동여부', '평토일구분코드']
    df[cols_to_ffill] = df[cols_to_ffill].ffill()
    return df

def pick_survey_activities(df: pd.DataFrame, gender: str, age_group: float, married: str, parent_child: str, is_working: str, day_type: str) -> List[str]:
    # 단순화를 위해 조건을 유연하게 검색
    filtered = df[
        (df['성별코드'] == gender) &
        (df['연령분류'] == age_group) &
        (df['결혼여부'] == married) &
        (df['평토일구분코드'] == day_type)
    ]
    if filtered.empty:
        # fallback
        filtered = df[(df['평토일구분코드'] == day_type)]

    activities = []
    for hour in range(24):
        hr_data = filtered[filtered['Hour'] == hour]
        if hr_data.empty:
            activities.append("수면 혹은 휴식")
        else:
            # 첫 번째 행동을 가져오거나 임의 선택
            acts = hr_data['Main_Activity_1'].dropna().tolist()
            if acts:
                activities.append(random.choice(acts))
            else:
                activities.append("수면 혹은 휴식")
    return activities


def _smooth_member_schedule(member_id: str, member_info: dict, raw_schedule_by_day: dict, model: Optional[str]) -> MemberProfile:
    system_role = "당신은 가상 스마트홈 시뮬레이션의 인물 스케줄 정보를 생성하는 AI입니다. 출력은 반드시 JSON이어야 합니다."
    
    prompt = f"""
    [구성원 정보]
    ID: {member_id}
    이름: {member_info['name']}
    역할: {member_info['role']}
    나이: {member_info['age']}
    경제상태: {member_info['economic_status']}
    특성: {member_info['traits']}
    
    [통계 기반 24시간 원시 활동(Raw Activities)]
    {json.dumps(raw_schedule_by_day, ensure_ascii=False, indent=2)}

    [작업 지시]
    1. 위의 1주일 치의 원시(Raw) 시간대별 활동 데이터를 참조하여, 이 구성원의 **1주일 (월~일, 총 7일)** 스케줄을 시간순으로 자연스럽게 생성하세요.
    2. 시간 간격은 가급적 **1시간 단위**로 하세요 (총 7 * 24 = 168개 정도의 항목 권장, 혹은 유의미한 행동 단위로 분리해도 됨 - 적어도 하루에 활동 시작~종료까지 포함). 월요일 시간은 `09-01 HH:MM` (임의로 9월 1일 월요일로 시작한다고 가정) ~ 일요일은 `09-07 HH:MM`으로 표기하세요. `time` 필드 예시: "09-01 08:00"
    3. `is_at_home` 값은 해당 활동이 집 안에서 이루어지는지 여부(Boolean)입니다. 수입노동, 외출 등은 false 입니다.

    [JSON 스키마 예시]
    {{
      "member_id": "{member_id}",
      "name": "{member_info['name']}",
      "role": "{member_info['role']}",
      "age": {member_info['age']},
      "economic_status": "{member_info['economic_status']}",
      "monthly_income": "{member_info['monthly_income']}",
      "traits": "{member_info['traits']}",
      "schedule": [
        {{"time": "09-01 07:00", "activity": "기상 및 아침 식사 준비", "is_at_home": true}},
        {{"time": "09-01 08:00", "activity": "출근 (이동)", "is_at_home": false}}
      ]
    }}
    """
    data = query_llm(prompt, system_role, model_schema=MemberProfile, model=model)
    return MemberProfile.parse_obj(data)


def generate_family_and_schedules(
    output_path: Path,
    survey_data_path: str = "생활시간조사.xlsx",
    model: Optional[str] = None
) -> Dict[str, Any]:
    logger.info("loading Survey Data for Schedules...")
    df = load_survey_data(str(survey_data_path))

    # 하드코딩된 예시 가족 셋업 (랜덤하게 3인 가구 생성)
    family_id = "fam_001"
    family_members_data = [
        {
            "member_id": "m_01", "name": "김철수", "role": "아빠(가구주)", "age": 45,
            "economic_status": "재직중", "monthly_income": "500만원 이상", "traits": "꼼꼼함, 전자기기 다루기를 좋아함",
            "survey_args": {"gender": "1(남성)", "age_group": 4.0, "married": "2(배우자있음)", "parent_child": "1(부모)", "is_working": "1(일하는중)"}
        },
        {
            "member_id": "m_02", "name": "이영희", "role": "엄마(배우자)", "age": 42,
            "economic_status": "재직중", "monthly_income": "300만원 이상", "traits": "깔끔함, 멀티태스킹 능함",
            "survey_args": {"gender": "2(여성)", "age_group": 4.0, "married": "2(배우자있음)", "parent_child": "1(부모)", "is_working": "1(일하는중)"}
        },
        {
            "member_id": "m_03", "name": "김민지", "role": "자녀(고등학생)", "age": 17,
            "economic_status": "학생", "monthly_income": "-", "traits": "소음에 민감함, 스마트폰 의존 높음",
            "survey_args": {"gender": "2(여성)", "age_group": 1.0, "married": "1(미혼)", "parent_child": "3(자녀)", "is_working": "3(무직)"}
        }
    ]

    members: List[MemberProfile] = []

    for mem in family_members_data:
        raw_schedule = {}
        s_args = mem["survey_args"]
        for day in range(1, 8):
            day_type = "1(평일)" if day <= 5 else ("2(토요일)" if day == 6 else "3(일요일)")
            acts = pick_survey_activities(
                df, s_args["gender"], s_args["age_group"], s_args["married"],
                s_args["parent_child"], s_args["is_working"], day_type
            )
            raw_schedule[f"Day_{day}_{day_type}"] = dict(enumerate(acts))
        
        # LLM을 활용해 1주일치 스케줄을 자연스럽게 보정
        prof = _smooth_member_schedule(mem["member_id"], mem, raw_schedule, model)
        members.append(prof)
        logger.info(f"Generated schedule for {mem['name']} ({mem['role']})")

    family_profile = FamilyProfile(family_id=family_id, members=members)
    
    # Save
    out_data = family_profile.dict()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(out_data, f, ensure_ascii=False, indent=2)

    logger.info("Family Profile generated at %s", output_path)
    return out_data