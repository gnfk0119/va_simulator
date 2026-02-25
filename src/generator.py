import json
import random
import pandas as pd
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

from src.schema import FamilyProfile, Environment, MemberProfile, ScheduleEvent, GeneratedFamily
from src.config import config
from utils.llm_client import LLMError, query_llm
from utils.logger import get_logger

logger = get_logger(__name__)

HOME_LAYOUT_SEED_PATHS = [
    Path("data/templates/home.json"),
    Path.home() / "Desktop" / "home.json",
]
FALLBACK_LAYOUT_TYPES = ["A", "B", "C", "D"]

SURVEY_PROFILE_COLUMNS = ["성별코드", "연령분류", "결혼여부", "부모자식여부", "경제활동여부", "평토일구분코드"]
SURVEY_ACTIVITY_COLUMNS = [
    "Hour",
    "Main_Activity_1",
    "Main_Activity_2",
    "Main_Activity_3",
    "Main_Ratio_1",
    "Main_Ratio_2",
    "Main_Ratio_3",
    "Sim_Activity_1",
    "Sim_Activity_2",
    "Sim_Activity_3",
    "Sim_Ratio_1",
    "Sim_Ratio_2",
    "Sim_Ratio_3",
]
SURVEY_RELEVANT_COLUMNS = SURVEY_PROFILE_COLUMNS + SURVEY_ACTIVITY_COLUMNS

WEEK_DAY_TYPES = {
    1: "1(평일)",
    2: "1(평일)",
    3: "1(평일)",
    4: "1(평일)",
    5: "1(평일)",
    6: "2(토요일)",
    7: "3(일요일)",
}

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


def _simple_power_device(name: str) -> Dict[str, Any]:
    return {
        "name": name,
        "properties": {
            "power": {"state_value": "off", "is_observable": True},
        },
    }


def _build_environment_fallback(picked_layout: str, layout_seed: Dict[str, Any]) -> Dict[str, Any]:
    rooms = layout_seed.get("rooms", [])
    room_names = []
    for room in rooms:
        if isinstance(room, dict) and room.get("name"):
            room_names.append(str(room["name"]))

    if not room_names:
        room_names = ["거실", "주방/식당", "안방", "침실2", "침실3", "욕실", "현관"]

    room_map: Dict[str, List[Dict[str, Any]]] = {}
    for room_name in room_names:
        devices = [
            _simple_power_device(f"{room_name} 메인 조명"),
            _simple_power_device(f"{room_name} 스위치"),
        ]

        if "거실" in room_name:
            devices.extend([
                _simple_power_device("스탠드형 에어컨"),
                _simple_power_device("스마트 TV"),
                _simple_power_device("로봇청소기"),
                _simple_power_device("월패드"),
            ])
        if "주방" in room_name or "식당" in room_name:
            devices.extend([
                _simple_power_device("냉장고"),
                _simple_power_device("김치냉장고"),
                _simple_power_device("전자레인지"),
                _simple_power_device("식기세척기"),
                _simple_power_device("주방 후드"),
            ])
        if "안방" in room_name or "침실" in room_name:
            devices.extend([
                _simple_power_device("벽걸이 에어컨"),
                _simple_power_device("공기청정기"),
            ])
        if "다용도실" in room_name or "서비스" in room_name:
            devices.extend([
                _simple_power_device("세탁기"),
                _simple_power_device("건조기"),
            ])

        room_map[room_name] = devices

    return {
        "type_name": picked_layout,
        "rooms": room_map,
    }


def _load_layout_seed_map() -> Dict[str, Dict[str, Any]]:
    for seed_path in HOME_LAYOUT_SEED_PATHS:
        if not seed_path.exists():
            continue
        try:
            data = json.loads(seed_path.read_text(encoding="utf-8"))
            unit_types = data.get("unit_types", [])
            seed_map = {u.get("type"): u for u in unit_types if isinstance(u, dict) and u.get("type")}
            if seed_map:
                logger.info("Loaded home layout seeds from %s", seed_path)
                return seed_map
        except Exception as exc:  # noqa: BLE001 - fallback below
            logger.warning("Failed to load layout seeds from %s: %s", seed_path, exc)

    logger.warning("home.json seed not found. Falling back to basic A~D type names.")
    return {t: {"type": t, "layout_summary": f"{t} 타입"} for t in FALLBACK_LAYOUT_TYPES}

def generate_environment(
    output_path: Path,
    model: Optional[str] = None,
    theme_hint: str = ""
) -> Dict[str, Any]:
    system_role = "당신은 스마트홈 연구용 데이터를 생성하는 도우미입니다. 모든 묘사와 대사는 한국어로 출력하세요. 반드시 JSON만 출력하세요."
    layout_seed_map = _load_layout_seed_map()
    picked_layout = random.choice(list(layout_seed_map.keys()))
    layout_seed = layout_seed_map[picked_layout]
    
    prompt_template = Path("prompts/generate_environment.txt").read_text(encoding="utf-8")
    prompt = prompt_template.format(
        picked_layout=picked_layout,
        theme_hint=theme_hint,
        layout_seed_json=json.dumps(layout_seed, ensure_ascii=False, indent=2)
    )

    try:
        data = query_llm(
            prompt,
            system_role,
            model_schema=Environment,
            model=model,
            max_retries=2,
            request_timeout=30.0,
        )
    except (LLMError, Exception) as exc:  # noqa: BLE001 - deterministic fallback for stability
        logger.warning("Environment generation fallback used: %s", exc)
        data = _build_environment_fallback(picked_layout, layout_seed)
        data = Environment.parse_obj(data).dict()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info("Environment generated at %s", output_path)
    return data


# --- 패밀리 및 스케줄 생성 로직 ---
def load_survey_data(survey_path: str = "생활시간조사.xlsx") -> pd.DataFrame:
    df = pd.read_excel(survey_path, sheet_name=0)
    cols_to_ffill = [c for c in SURVEY_PROFILE_COLUMNS if c in df.columns]
    df[cols_to_ffill] = df[cols_to_ffill].ffill()
    return df

def _filter_survey_rows_for_day(
    df: pd.DataFrame,
    gender: str,
    age_group: float,
    married: str,
    parent_child: str,
    is_working: str,
    day_type: str,
) -> Dict[str, Any]:
    criteria = {
        "성별코드": gender,
        "연령분류": age_group,
        "결혼여부": married,
        "부모자식여부": parent_child,
        "경제활동여부": is_working,
        "평토일구분코드": day_type,
    }

    day_df = df[df["평토일구분코드"] == day_type].copy()
    if day_df.empty:
        day_df = df.copy()

    match_columns: List[str] = []
    for col, val in criteria.items():
        if col not in day_df.columns:
            continue
        match_col = f"_match_{col}"
        day_df[match_col] = (day_df[col] == val).astype(int)
        match_columns.append(match_col)

    if match_columns:
        day_df["_match_score"] = day_df[match_columns].sum(axis=1)
        best_score = int(day_df["_match_score"].max())
        filtered = day_df[day_df["_match_score"] == best_score].copy()
    else:
        best_score = 0
        filtered = day_df.copy()

    selected_cols = [c for c in SURVEY_RELEVANT_COLUMNS if c in filtered.columns]
    filtered = filtered[selected_cols].sort_values(by=["Hour"]).reset_index(drop=True)
    rows = json.loads(filtered.to_json(orient="records", force_ascii=False))

    return {
        "criteria": criteria,
        "best_match_score": best_score,
        "row_count": len(rows),
        "rows": rows,
    }


def _build_member_survey_dataset(df: pd.DataFrame, survey_args: Dict[str, Any]) -> Dict[str, Any]:
    period = config["simulation"].get("period", "일주일 전체")
    
    if period == "일주일 전체":
        day_types = ["1(평일)", "2(토요일)", "3(일요일)"]
        week_mapping = {f"Day_{day}": WEEK_DAY_TYPES[day] for day in range(1, 8)}
    elif period == "평일만":
        day_types = ["1(평일)"]
        week_mapping = {"Day_1": WEEK_DAY_TYPES[1]}
    elif period == "금토일":
        day_types = ["1(평일)", "2(토요일)", "3(일요일)"]
        week_mapping = {"Day_5": WEEK_DAY_TYPES[5], "Day_6": WEEK_DAY_TYPES[6], "Day_7": WEEK_DAY_TYPES[7]}
    else: # "일요일"
        day_types = ["3(일요일)"]
        week_mapping = {"Day_7": WEEK_DAY_TYPES[7]}

    filtered_by_day_type: Dict[str, Any] = {}
    for day_type in day_types:
        filtered_by_day_type[day_type] = _filter_survey_rows_for_day(
            df=df,
            gender=survey_args["gender"],
            age_group=survey_args["age_group"],
            married=survey_args["married"],
            parent_child=survey_args["parent_child"],
            is_working=survey_args["is_working"],
            day_type=day_type,
        )

    return {
        "week_day_mapping": week_mapping,
        "filtered_data_by_day_type": filtered_by_day_type,
    }


def _infer_is_at_home(activity: str) -> bool:
    text = (activity or "").strip()
    if not text:
        return True
    return not any(keyword in text for keyword in OUT_OF_HOME_KEYWORDS)


def _build_hourly_activity_fallback(day_payload: Dict[str, Any]) -> Dict[int, str]:
    rows = day_payload.get("rows", []) if isinstance(day_payload, dict) else []
    hourly: Dict[int, str] = {}
    for row in rows:
        try:
            hour = int(row.get("Hour"))
        except Exception:
            continue
        if not (0 <= hour <= 23):
            continue

        activity = (
            row.get("Main_Activity_1")
            or row.get("Main_Activity_2")
            or row.get("Main_Activity_3")
            or "수면 혹은 휴식"
        )
        hourly[hour] = str(activity)
    return hourly


def _normalize_schedule_to_full_week(profile: MemberProfile, survey_dataset: Dict[str, Any]) -> MemberProfile:
    existing_hourly: Dict[str, ScheduleEvent] = {}
    for event in profile.schedule:
        try:
            dt = datetime.strptime(event.time.strip(), "%m-%d %H:%M")
            key = dt.strftime("%m-%d %H:00")
        except Exception:
            continue
        if key not in existing_hourly:
            existing_hourly[key] = ScheduleEvent(
                time=key,
                activity=event.activity,
                is_at_home=bool(getattr(event, "is_at_home", True)),
            )

    by_day_type = survey_dataset.get("filtered_data_by_day_type", {})
    fallback_cache: Dict[str, Dict[int, str]] = {}
    for day_type, payload in by_day_type.items():
        fallback_cache[day_type] = _build_hourly_activity_fallback(payload)

    period = config["simulation"].get("period", "일주일 전체")
    if period == "일주일 전체":
        day_range = range(1, 8)
    elif period == "평일만":
        day_range = range(1, 2)
    elif period == "금토일":
        day_range = range(5, 8)
    else: # "일요일"
        day_range = range(7, 8)

    normalized_schedule: List[ScheduleEvent] = []
    for day in day_range:
        day_type = WEEK_DAY_TYPES[day]
        fallback_hourly = fallback_cache.get(day_type, {})
        for hour in range(24):
            time_str = f"09-{day:02d} {hour:02d}:00"
            if time_str in existing_hourly:
                normalized_schedule.append(existing_hourly[time_str])
                continue

            activity = fallback_hourly.get(hour, "수면 혹은 휴식")
            normalized_schedule.append(
                ScheduleEvent(
                    time=time_str,
                    activity=activity,
                    is_at_home=_infer_is_at_home(activity),
                )
            )

    profile.schedule = normalized_schedule
    return profile


def _build_member_profile_fallback(member_id: str, member_info: dict, survey_dataset: dict) -> MemberProfile:
    by_day_type = survey_dataset.get("filtered_data_by_day_type", {})
    fallback_cache: Dict[str, Dict[int, str]] = {}
    for day_type, payload in by_day_type.items():
        fallback_cache[day_type] = _build_hourly_activity_fallback(payload)

    period = config["simulation"].get("period", "일주일 전체")
    if period == "일주일 전체":
        day_range = range(1, 8)
    elif period == "평일만":
        day_range = range(1, 6)
    elif period == "금토일":
        day_range = range(5, 8)
    else: # "일요일"
        day_range = range(7, 8)

    schedule: List[ScheduleEvent] = []
    for day in day_range:
        day_type = WEEK_DAY_TYPES[day]
        hourly = fallback_cache.get(day_type, {})
        for hour in range(24):
            activity = hourly.get(hour, "수면 혹은 휴식")
            schedule.append(
                ScheduleEvent(
                    time=f"09-{day:02d} {hour:02d}:00",
                    activity=activity,
                    is_at_home=_infer_is_at_home(activity),
                )
            )

    return MemberProfile(
        member_id=member_id,
        name=member_info["name"],
        role=member_info["role"],
        age=member_info["age"],
        economic_status=member_info["economic_status"],
        monthly_income=member_info["monthly_income"],
        bio=member_info["bio"],
        schedule=schedule,
    )


def _smooth_member_schedule(member_id: str, member_info: dict, survey_dataset: dict, model: Optional[str]) -> MemberProfile:
    system_role = "당신은 가상 스마트홈 시뮬레이션의 인물 스케줄 정보를 생성하는 AI입니다. 출력은 반드시 JSON이어야 합니다."
    
    period = config["simulation"].get("period", "일주일 전체")
    if period == "일주일 전체":
        instructions = "1. 위의 필터링 데이터 전체를 참조하여, 이 구성원의 **1주일 (월~일, 총 7일)** 스케줄을 시간순으로 자연스럽게 생성하세요.\n    2. 시간 간격은 가급적 **1시간 단위**로 하세요 (총 7 * 24 = 168개). 월요일 시간은 `09-01 HH:MM` ~ 일요일은 `09-07 HH:MM`으로 표기하세요. `time` 필드 예시: \"09-01 08:00\""
    elif period == "평일만":
        instructions = "1. 위의 필터링 데이터 전체를 참조하여, 이 구성원의 **자신의 평일 단 하루 (월요일, Day_1)** 스케줄을 시간순으로 자연스럽게 생성하세요.\n    2. 시간 간격은 가급적 **1시간 단위**로 하세요 (총 1 * 24 = 24개). 월요일 시간은 `09-01 HH:MM`으로 표기하세요. `time` 필드 예시: \"09-01 08:00\""
    elif period == "금토일":
        instructions = "1. 위의 필터링 데이터 전체를 참조하여, 이 구성원의 **금, 토, 일 3일 (Day_5 ~ Day_7)** 스케줄을 시간순으로 자연스럽게 생성하세요.\n    2. 시간 간격은 가급적 **1시간 단위**로 하세요 (총 3 * 24 = 72개). 금요일 시간은 `09-05 HH:MM` ~ 일요일은 `09-07 HH:MM`으로 표기하세요. `time` 필드 예시: \"09-05 08:00\""
    else: # "일요일"
        instructions = "1. 위의 필터링 데이터 전체를 참조하여, 이 구성원의 **일요일(Day_7)** 스케줄을 시간순으로 자연스럽게 생성하세요.\n    2. 시간 간격은 가급적 **1시간 단위**로 하세요. 일요일 시간은 `09-07 HH:MM`으로 표기하세요. `time` 필드 예시: \"09-07 08:00\""

    prompt_template = Path("prompts/generate_schedule.txt").read_text(encoding="utf-8")
    prompt = prompt_template.format(
        member_id=member_id,
        name=member_info['name'],
        role=member_info['role'],
        age=member_info['age'],
        economic_status=member_info['economic_status'],
        monthly_income=member_info['monthly_income'],
        bio=member_info['bio'],
        period=period,
        week_day_mapping_json=json.dumps(survey_dataset['week_day_mapping'], ensure_ascii=False, indent=2),
        filtered_data_json=json.dumps(survey_dataset['filtered_data_by_day_type'], ensure_ascii=False, indent=2),
        instructions=instructions
    )
    try:
        data = query_llm(
            prompt,
            system_role,
            model_schema=MemberProfile,
            model=model,
            max_retries=2,
            request_timeout=30.0,
        )
        profile = MemberProfile.parse_obj(data)
        return _normalize_schedule_to_full_week(profile, survey_dataset)
    except (LLMError, Exception) as exc:  # noqa: BLE001 - deterministic fallback for stability
        logger.warning("Schedule generation fallback used for %s: %s", member_info["name"], exc)
        return _build_member_profile_fallback(member_id, member_info, survey_dataset)


def _map_generated_family_to_survey_args(gen_family: GeneratedFamily) -> List[Dict[str, Any]]:
    members_data = []
    
    for idx, mem in enumerate(gen_family.members):
        # 1. gender mapping
        gender_code = "1(남성)" if mem.gender == "남성" else "2(여성)"
        
        # 2. age mapping (e.g., 45 -> 4.0, 18 -> 1.0)
        age_group = float(mem.age // 10)
        if age_group < 1.0:
            age_group = 1.0 # survey data minimum
        
        # 3. married / parent_child mapping based on role loosely
        if "부" in mem.role or "모" in mem.role or "가구주" in mem.role or "배우자" in mem.role:
            married_code = "2(배우자있음)"
            parent_child_code = "1(부모)"
        else:
            married_code = "1(미혼)"
            parent_child_code = "3(자녀)"
            
        # 4. working status
        working_code = "1(일하는중)" if mem.is_working else "2(일안함)"
        
        members_data.append({
            "member_id": f"m_{idx+1:02d}",
            "name": mem.name,
            "role": mem.role,
            "age": mem.age,
            "economic_status": mem.economic_status,
            "monthly_income": mem.monthly_income,
            "bio": mem.bio,
            "survey_args": {
                "gender": gender_code,
                "age_group": age_group,
                "married": married_code,
                "parent_child": parent_child_code,
                "is_working": working_code
            }
        })
        
    return members_data


def _generate_random_family(model: Optional[str]) -> List[Dict[str, Any]]:
    rules = config.get("simulation", {}).get("family_generation", {}).get("random_constraints", {})
    size_min = rules.get("size_min", 2)
    size_max = rules.get("size_max", 4)
    location = rules.get("location", "수도권 및 시 지역")
    income = rules.get("min_monthly_income_krw", 4000000)
    
    system_role = "당신은 가상 스마트홈 시뮬레이션의 가구(가족) 구성원을 무작위로 생성하는 AI입니다. 출력은 반드시 JSON이어야 합니다."
    prompt_template = Path("prompts/generate_random_family.txt").read_text(encoding="utf-8")
    prompt = prompt_template.format(
        size_min=size_min,
        size_max=size_max,
        location=location,
        income=income
    )
    
    result = query_llm(prompt, system_role, model_schema=GeneratedFamily, model=model)
    # LLM might occasionally wrap with {"family": [...]} or similar if strict mode fails.
    if isinstance(result, dict) and "family" in result and "members" not in result:
        result["members"] = result.pop("family")
    gen_family = GeneratedFamily.parse_obj(result)
    logger.info("Successfully generated random family structure via LLM.")
    return _map_generated_family_to_survey_args(gen_family)


def _generate_prompt_family(model: Optional[str], instruction: str) -> List[Dict[str, Any]]:
    system_role = "당신은 가상 스마트홈 시뮬레이션의 가구(가족) 구성원을 사용자의 시드 자연어에 기반하여 생성하는 AI입니다. 출력은 반드시 JSON이어야 합니다."
    prompt_template = Path("prompts/generate_prompt_family.txt").read_text(encoding="utf-8")
    prompt = prompt_template.format(instruction=instruction)
    
    result = query_llm(prompt, system_role, model_schema=GeneratedFamily, model=model)
    if isinstance(result, dict) and "family" in result and "members" not in result:
        result["members"] = result.pop("family")
    gen_family = GeneratedFamily.parse_obj(result)
    logger.info(f"Successfully generated family structure via prompt: {instruction}")
    return _map_generated_family_to_survey_args(gen_family)


def _get_template_family(template_name: str) -> List[Dict[str, Any]]:
    # 기본 템플릿(하드코딩 폴백)
    if template_name == "default_couple":
        return [
            {
                "member_id": "m_01", "name": "김철수", "role": "아빠(가구주)", "age": 45,
                "economic_status": "재직중", "monthly_income": "500만원 이상",
                "bio": "김철수는 45세 직장인으로 평일에는 업무 중심의 생활을 한다. "
                       "퇴근 후에는 집안 전자기기를 직접 만지며 상태를 점검하는 편이다. "
                       "가족의 생활 리듬을 맞추기 위해 저녁 시간에는 주로 거실과 주방에서 시간을 보낸다. "
                       "조용하고 효율적인 환경을 선호해 기기 제어 명령을 자주 사용한다.",
                "survey_args": {"gender": "1(남성)", "age_group": 4.0, "married": "2(배우자있음)", "parent_child": "1(부모)", "is_working": "1(일하는중)"}
            },
            {
                "member_id": "m_02", "name": "이영희", "role": "엄마(배우자)", "age": 42,
                "economic_status": "재직중", "monthly_income": "300만원 이상",
                "bio": "이영희는 42세로 일과 가사를 병행하며 하루 일정을 촘촘하게 운영한다. "
                       "주방과 세탁 공간에서 동시에 여러 작업을 처리하는 경우가 많다. "
                       "가족의 식사와 생활 편의를 챙기기 위해 시간대별로 집안 기기 사용 패턴이 뚜렷하다. "
                       "상황에 따라 조명과 주방 기기를 빠르게 제어하는 성향이 있다.",
                "survey_args": {"gender": "2(여성)", "age_group": 4.0, "married": "2(배우자있음)", "parent_child": "1(부모)", "is_working": "1(일하는중)"}
            }
        ]
    
    logger.warning(f"Template '{template_name}' not found. Falling back to default_couple.")
    return _get_template_family("default_couple")


def generate_family_and_schedules(
    output_path: Path,
    survey_data_path: str = "생활시간조사.xlsx",
    model: Optional[str] = None
) -> Dict[str, Any]:
    logger.info("loading Survey Data for Schedules...")
    df = load_survey_data(str(survey_data_path))

    fam_gen_config = config.get("simulation", {}).get("family_generation", {})
    gen_mode = fam_gen_config.get("mode", "template")

    family_id = "fam_001"
    
    if gen_mode == "random":
        family_members_data = _generate_random_family(model)
    elif gen_mode == "prompt":
        instruction = fam_gen_config.get("prompt_instruction", "2인 부부")
        family_members_data = _generate_prompt_family(model, instruction)
    else:
        # Default fallback is template
        template_name = fam_gen_config.get("template_name", "default_couple")
        family_members_data = _get_template_family(template_name)

    members: List[MemberProfile] = []

    for mem in family_members_data:
        s_args = mem["survey_args"]
        survey_dataset = _build_member_survey_dataset(df, s_args)
        
        # LLM을 활용해 필터링 데이터 기반 1주일치 스케줄 생성
        prof = _smooth_member_schedule(mem["member_id"], mem, survey_dataset, model)
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
