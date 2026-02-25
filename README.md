# VA Simulator

가상 가구의 주간 생활 스케줄을 생성하고, 스마트홈 VA 상호작용을 **4-Cell Matrix (Context 유/무 x 기반/통제형 VA)** 방식으로 시뮬레이션하여 자기/관찰자 평가를 기록 및 추출하는 연구용 프레임워크입니다.

## 1. 개요 및 설치

Python 3.12를 권장합니다. 가상환경(Virtual Environment) 세팅 후 패키지를 설치하는 것을 권장합니다.

```bash
# 1) 가상환경 생성 (최초 1회)
python3.12 -m venv .venv

# 2) 가상환경 활성화 (Mac/Linux)
source .venv/bin/activate
# Windows의 경우: .venv\Scripts\activate

# 3) 패키지 설치
pip install -r requirements.txt
```

루트 디렉토리의 `.env` 파일에 각 LLM 제공자용 키를 기재해야 합니다. (예: `OPENAI_API_KEY`, `GEMINI_API_KEY`)

## 2. 설정 및 실행 방법

`config.yaml`을 통해 LLM 모델 분배, 실행 Run ID, 스케줄 범위 등을 편리하게 지정할 수 있습니다.
최상단의 `run.name` 을 변경하여 시뮬레이션 세트를 독립적으로 유지할 수 있습니다. (예: `run_name: "pilot_2026-02-26_A"`)

지원되는 실행 모드는 `generate`, `simulate`, `evaluate` 3가지입니다.

```bash
# 1) 환경 + 가족/스케줄 생성 (config.yaml의 run_name 경로에 폴더 생성됨)
python main.py --mode generate

# 2) 15분 단위 시뮬레이션 및 4-Cell 매트릭스 실행
python main.py --mode simulate

# 3) 제 3자(관찰자) 평가 로직 실행 및 엑셀(export) 자동 추출
python main.py --mode evaluate
```

> **단축 팁: 생성부터 평가결과 추출까지 백그라운드에서 모두 실행하려면:**
> ```bash
> python main.py --mode generate && python main.py --mode simulate && python main.py --mode evaluate
> ```
> 
> **[🔥 ALL-IN-ONE] 생성부터 평가, 그리고 엑셀 추출물에 대한 사용자 타입 매칭(Type Match)까지 원스톱 일괄 실행:**
> 시뮬레이션 결과물은 `data/{run_name}/exports` 아래 저장됩니다. 아래 경로의 `run_name` 부분을 현재 config에 맞춰 수정한 후 실행하세요.
> *(아래 예시는 config.yaml 의 run_name이 `pilot_3.2`이고, 가족 0번의 엑셀 데이터인 경우입니다)*
> ```bash
> python main.py --mode generate && python main.py --mode simulate && python main.py --mode evaluate && python scripts/match_assign.py data/pilot_3.2/exports/run_0/3_interaction_history.xlsx
> ```

## 3. 핵심 시스템 아키텍처

### 3.1 LLM 프롬프트 외연화
모든 LLM 프롬프트는 하드코딩되지 않으며 `prompts/` 디렉토리 하위의 `.txt` 파일에 정의되어 있어, 프롬프트 엔지니어링 및 유지보수에 용이합니다.

### 3.2 4-Cell Simulation Matrix (`src/simulator.py`)
에이전트별 매 틱(15분 단위)마다 다음 4개의 인스턴스로 분기하여 상호작용을 테스트합니다:
1. **WC x VA_C** (맥락 O / 생성형 코어) - **가장 기본 타임라인 (상태 보존)**
2. **WC x VA_R** (맥락 O / 통제형 기반) - 분석 격리 모델
3. **WOC x VA_C** (맥락 X / 생성형 코어) - 분석 격리 모델
4. **WOC x VA_R** (맥락 X / 통제형 기반) - 분석 격리 모델

> **VA_C vs VA_R**
> - **VA_C (`src/va_baseline.py`)**: 사용자 명령을 바탕으로 LLM이 자유롭게 상황을 해석하고 조작하는 생성형 기반 VA입니다.
> - **VA_R (`src/va_r.py`)**: NLU 분류기(Gemini)와 `data/domain_intent_labels_defs.csv`를 통해 인텐트를 먼저 강제 분류한 후, 엄격한 코드 룰(Rule)에 의해 기기를 조작하고 응답만 생성하는 제한적 VA입니다.

### 3.3 아바타별 독립 메모리 (Storage Subsystem)
`MemorySystem`은 시뮬레이션 중에 생성되는 과거 액션이나 발화 내역을 아바타(`member_id`)별로 엄격하게 격리합니다. 각 메모리는 `weight`(가중치)를 가지며, 시간당 `0.05`씩 자동 감소하여 최근 기억을 우선적으로 회상합니다 (최하점: `0.2`).

### 3.4 평가 추론(TE) 및 추출 (Export Pipeline)
- `src/evaluator.py`: 각 4-Cell 로깅에 대하여 제 3자(관찰자) 평가를 생성하여 삽입합니다.
- `src/exporter.py`: 완료된 로그에서 엑셀 파일들을 축출합니다 (`data/{run_name}/exports/`).
  - `1_family_info.xlsx`
  - `2_memory_history.xlsx`
  - **`3_interaction_history.xlsx`**: 각 모드별 (Command, VA Response, State Changes, SE, TE) 항목과 **Gap (SE-TE)** 계산, **BG/SG 판별값**을 한 행(row)에 모두 정렬하여 출력합니다.

### 3.5 타입 매칭 강제 할당 스크립트 (Scripts)
추출이 끝난 위 3번 엑셀 산출물에 대하여 `scripts/match_assign.py`를 실행할 수 있습니다.
```bash
python scripts/match_assign.py "data/pilot_2026/exports/3_interaction_history.xlsx"
```
해당 스크립트는 4-Cell 각각의 BG/SG 분포를 분석하여 Interaction Type(A, B, C, D)을 기본적으로 자동 할당(Auto Type)해 주며, 연구자가 별도로 덮어쓸 수 있도록 `_matched.xlsx` 사본을 만들어 냅니다.

## 4. 파일 입출력 트랙
- `data/templates/home.json` (기초 건물 데이터 시드)
- `data/domain_intent_labels_defs.csv` (VA_R을 위한 규칙 매핑 스키마)
- 결과 및 로그물 출력 디렉토리: `data/{run_name}/`
