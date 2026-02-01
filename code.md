제시된 요구사항을 완벽하게 반영하여, **타 개발자가 즉시 구현에 착수할 수 있는 수준의 상세 코딩 계획(Technical Design Document)**을 작성했습니다.

이 문서는 프로젝트 구조, 데이터 스키마, 핵심 모듈별 구현 로직, 프롬프트 전략까지 포함하고 있습니다.

---

```markdown
# Project Plan: Smart Home Evaluation Gap Simulator
**Objective:** 1인칭(발화자)과 3인칭(관찰자)의 음성 에이전트 경험 평가 간극을 연구하기 위한 텍스트 기반 시뮬레이터 개발.
**Methodology:** AgentSense의 데이터 생성 방식(환경/페르소나) + GIDEA의 시뮬레이션 루프 결합.

---

## 1. 프로젝트 디렉토리 구조 (Project Structure)

```text
smart_home_sim/
├── data/
│   ├── templates/          # AgentSense 기반 기본 템플릿 (rooms, objects)
│   ├── generated/          # 생성된 정적 데이터 (Phase 1 결과물)
│   │   ├── environment.json
│   │   └── avatar_profile.json
│   └── logs/               # 시뮬레이션 결과 (Phase 2, 3 결과물)
│       ├── simulation_log_full.json
│       └── evaluation_result.json
├── src/
│   ├── __init__.py
│   ├── schema.py           # Pydantic 데이터 모델 정의 (핵심)
│   ├── generator.py        # Phase 1: 환경 및 페르소나 생성
│   ├── simulator.py        # Phase 2: 시뮬레이션 루프 및 1인칭 평가
│   ├── evaluator.py        # Phase 3: 제 3자 평가
│   └── va_agent.py         # 가상 음성 비서 로직 (상태 업데이트 처리)
├── utils/
│   ├── llm_client.py       # OpenAI API Wrapper (JSON 강제 출력 포함)
│   └── logger.py           # 로깅 유틸리티
├── main.py                 # 실행 진입점
├── requirements.txt
└── .env                    # OPENAI_API_KEY 저장

```

---

## 2. 데이터 스키마 정의 (`src/schema.py`)

개발의 혼동을 막기 위해 데이터 구조를 먼저 정의합니다.

```python
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

# --- Phase 1: Environment & Profile ---
class DeviceState(BaseModel):
    state_value: str = Field(..., description="현재 상태 (e.g., 'on', 'off', '24도')")
    is_observable: bool = Field(True, description="제 3자가 눈으로 상태를 확인할 수 있는지 여부")

class RoomObject(BaseModel):
    name: str
    properties: Dict[str, DeviceState]  # 예: {"power": {"state_value": "on", ...}}

class Environment(BaseModel):
    rooms: Dict[str, List[RoomObject]]  # Room Name -> Object List

class ScheduleEvent(BaseModel):
    time: str
    activity: str

class AvatarProfile(BaseModel):
    name: str
    traits: str  # 성격 묘사
    schedule: List[ScheduleEvent]

# --- Phase 2: Simulation Log ---
class StateChange(BaseModel):
    device_name: str
    property_name: str
    before: str
    after: str

class InteractionLog(BaseModel):
    time: str
    # Inputs for 1st Person
    visible_action: str
    hidden_context: str
    
    # Interaction
    command: str
    va_response: str
    state_changes: List[StateChange]
    
    # Evaluation
    self_rating: int
    self_reason: str
    
    # 3rd Person Evaluation (Filled in Phase 3)
    observer_rating: Optional[int] = None
    observer_reason: Optional[str] = None

```

---

## 3. 모듈별 상세 구현 계획

### Module 1: 기반 데이터 생성 (`src/generator.py`)

AgentSense의 방식을 차용하여 초기 데이터를 생성합니다.

* **Function:** `generate_environment()`
* **Logic:** LLM에게 "한국의 일반적인 30평대 아파트 구조와 IoT 기기 리스트"를 요청.
* **Prompt Key:** 각 기기의 `is_observable` 속성을 정의하도록 지시 (예: 스마트 플러그의 내부 전류량=False, 거실 전등=True).
* **Output:** `data/generated/environment.json` 저장.


* **Function:** `generate_avatar()`
* **Logic:** LLM을 이용해 페르소나(이름, 성격, 직업)와 일주일치 스케줄(Time, Activity) 생성.
* **Output:** `data/generated/avatar_profile.json` 저장.



### Module 2: 시뮬레이션 엔진 (`src/simulator.py`)

GIDEA의 루프 구조를 따르되, **Action과 Context의 분리**에 집중합니다.

* **Class:** `SimulationEngine`
* **Init:** `environment.json`, `avatar_profile.json` 로드.
* **Loop:** `avatar_profile.schedule`을 순회하며 `run_step()` 실행.


* **Function:** `run_step(time, activity)`
1. **Action & Context Generation (LLM)**
* **Prompt:** "현재 시간 {time}, 활동 {activity}. 이 활동을 수행하는 구체적인 '겉보기 행동(Visible Action)'과, 행동의 제약이나 내면의 의도가 담긴 '속마음(Hidden Context)'을 분리해서 JSON으로 생성해."


2. **Feasibility Check**
* `Visible Action`이 '수면', '양치 중' 등 발화 불가능 상태인지 체크 (LLM 판단 혹은 키워드 매칭). 불가능하면 Skip.


3. **Command Generation (LLM)**
* **Input:** `Hidden Context`, `Visible Action`.
* **Prompt:** "당신은 지금 {Hidden Context} 상황입니다. 이 상황을 해결하거나 돕기 위해 스마트홈 VA에게 할 자연스러운 한국어 명령을 생성하세요."


4. **VA Execution (`src/va_agent.py` 호출)**
* **Input:** `Command`, `Current Environment`.
* **Logic:** 명령어를 분석해 `Environment` 상태 업데이트(Dict 조작) -> 변경 내역(`StateChange`) 및 응답(`Response`) 반환.


5. **Self-Evaluation (LLM)**
* **Input:** `Hidden Context`, `StateChange`, `Command`, `Response`.
* **Prompt:**
```text
[상황] 속마음: {Hidden Context}
[결과] 기기 변화: {StateChange}
[대화] 나: "{Command}" / VA: "{Response}"

위 정보를 종합할 때, 본인의 의도가 얼마나 잘 충족되었습니까? (1-7점)

```




6. **Log Save:** `data/logs/simulation_log_full.json`에 append.



### Module 3: 제 3자 평가 시스템 (`src/evaluator.py`)

평가 간극(Gap)을 측정하기 위한 모듈입니다.

* **Function:** `run_observer_evaluation()`
1. `simulation_log_full.json` 로드.
2. 각 로그 항목에 대해:
* **Information Masking:** `Hidden Context` 삭제. `StateChange`를 "관측 가능한 텍스트"(예: TV가 켜졌다)로 변환.
* **Observer Prompt:**
```text
[관찰 데이터]
- 행동: {Visible Action}
- 관측된 결과: {Observable State Change}
- 대화: 사용자="{Command}" / VA="{Response}"

CCTV로 지켜보는 제 3자 입장에서, 이 상호작용이 얼마나 자연스럽고 적절해 보입니까? (1-7점)

```




3. 결과를 `observer_rating` 필드에 업데이트하여 `data/logs/evaluation_result.json` 저장.



---

## 4. 유틸리티 및 LLM 클라이언트 (`src/utils/llm_client.py`)

* **Role:** 모든 LLM 호출을 담당하며, JSON 형식을 강제함 (OpenAI `response_format={"type": "json_object"}` 활용).
* **Dependencies:** `openai`, `dotenv`.
* **Key Function:**
```python
def query_llm(prompt: str, system_role: str, model_schema: BaseModel = None) -> Dict:
    # Pydantic 모델을 스키마로 전달하거나, JSON 모드로 호출 후 파싱
    pass

```



---

## 5. 실행 흐름 (Workflow Execution)

개발자는 아래 순서대로 스크립트를 실행하여 전체 연구를 수행합니다.

1. **Setup:** `.env` 파일에 API 키 설정.
2. **Step 1 (Data Gen):** `python main.py --mode generate`
* 환경 파일과 아바타 프로필 생성됨.


3. **Step 2 (Simulate):** `python main.py --mode simulate`
* 스케줄에 따라 시뮬레이션 수행.
* 1인칭 평가까지 완료된 `simulation_log_full.json` 생성.


4. **Step 3 (Evaluate):** `python main.py --mode evaluate`
* 3인칭 평가 수행.
* 최종적으로 `evaluation_result.json` 생성 (Gap 분석 가능).



---

## 6. 개발 체크리스트 (Implementation Checklist)

* [ ] **환경 설정:** Python 3.9+, Virtualenv 설정.
* [ ] **스키마 확정:** `src/schema.py`의 필드명 확정 (나중에 바꾸면 파싱 에러 잦음).
* [ ] **프롬프트 튜닝:**
* [ ] `Visible Action` 생성 시 지나치게 의도를 드러내지 않도록 주의 (Action은 건조하게 묘사).
* [ ] `Hidden Context` 생성 시 구체적인 불편함(손이 젖음, 리모컨이 멂 등)을 포함하도록 유도.


* [ ] **VA 로직 구현:** 실제 IoT 연결 없이, 텍스트 명령을 `Environment` 딕셔너리 업데이트로 매핑하는 간단한 Rule-based 또는 LLM-based 파서 구현.
* [ ] **한국어 처리:** 모든 프롬프트의 Output 예시를 한국어로 작성하여 답변 고정.

```

이 계획서는 바로 프로젝트 폴더를 생성하고 `src/schema.py`부터 작성을 시작할 수 있도록 구조화되었습니다.

```

---
### 실행 방법:

python main.py --mode generate

python main.py --mode simulate

python main.py --mode evaluate
