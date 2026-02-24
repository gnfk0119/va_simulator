# VA Simulator

가상 가구의 주간 생활 스케줄을 생성하고, 스마트홈 VA 상호작용을 `맥락 포함/맥락 미포함` 두 방식으로 실행해 1인칭/3인칭 평가를 기록하는 연구용 시뮬레이터입니다.

## 1. 설치

Python 3.12 권장

```bash
pip install -r requirements.txt
```

`.env` 파일에 `OPENAI_API_KEY`를 설정해야 합니다.

## 2. 실행 방법

`config.yaml`의 `simulation.period` 항목을 통해 시뮬레이션 기간을 설정할 수 있습니다:
- `"일주일 전체"` (7일)
- `"평일만"` (단일 월요일, 24시간)
- `"일요일"` (단일 일요일, 24시간)

지원되는 실행 모드는 `generate`, `simulate`, `evaluate` 3가지입니다.

```bash
# 1) 환경 + 가족/스케줄 생성
python main.py --mode generate

# 2) 15분 단위 시뮬레이션 실행
python main.py --mode simulate

# 3) 관찰자 평가 + 엑셀 추출
python main.py --mode evaluate
```

세 단계를 한 번에 실행하려면:

```bash
source .venv/bin/activate
python main.py --mode generate && \
python main.py --mode simulate && \
python main.py --mode evaluate
```

모델을 바꾸고 싶으면:

```bash
python main.py --mode generate --model gpt-4o
```

## 3. 현재 알고리즘

### 3.1 Generate (`src/generator.py`)

- 환경 생성:
  - `A/B/C/D` 타입 중 하나를 선택합니다.
  - 타입 시드는 `home.json`에서 읽습니다.
  - 시드 탐색 순서:
    - `data/templates/home.json`
    - `~/Desktop/home.json`
  - 시드의 `rooms[].name`을 참고하여 해당 구조를 LLM이 구체화합니다.

- 가족/스케줄 생성:
  - 통계청 생활시간조사(`생활시간조사.xlsx`)를 읽습니다.
  - 구성원 조건(성별/연령/결혼/부모자식/경제활동 + 요일타입)과의 매칭 점수를 계산합니다.
  - 요약 통계가 아니라, **필터된 관련 row 전체**를 LLM 프롬프트에 전달합니다.
  - 월~일(7일) 매핑은 `Day_1..Day_7 -> 평일/토요일/일요일`로 전달하고, 최종 스케줄은 9월 포맷(`09-01 HH:MM`)으로 생성합니다.

### 3.2 Simulate (`src/simulator.py`)

- 1시간 스케줄 이벤트를 15분(`0, 15, 30, 45`) 단위로 분할해 타임라인을 만듭니다.
- 각 스텝에서:
  - `hourly_activity` (1시간 대분류) 및 `quarterly_activity` (15분 단위 행동 요약) 로그 생성
  - `concrete_action` (해당 15분을 구성하는 최소 3문장 이상의 순차적인 구체적 행동 묘사) 생성
  - `latent_command` (실제 VA 명령 형태의 잠재 명령) 생성
  - 필요 시 VA 명령 실행 및 응답, 기기 상태 변화, 상태 변화 자연어 묘사(`state_change_description`) 기록
- 기존 `visible_action`, `hidden_context` 분리 구조는 사용하지 않습니다.
- 메모리 시스템:
  - 15분 단위의 활동 요약(`quarterly_activity`) 및 VA 호출이 메모리에 기록됩니다.
  - 시간 경과에 따라 decay 가중치가 감소합니다(최저 0.3).

### 3.3 Evaluate (`src/evaluator.py`)

- 평가자는 아래 2가지 정보만 사용합니다.
  - 사용자 명령 문장 + VA 응답
  - 상태 변화 설명(`state_change_description`)
- `with_context`, `without_context` 각각에 대해 `observer_rating`, `observer_reason`을 채웁니다.

### 3.4 Export (`src/exporter.py`)

`evaluate` 후 자동으로 run별 엑셀 3종을 생성합니다.

- `1_family_info.xlsx`: 가구원 기본 정보 및 프로필
- `2_memory_history.xlsx`: 시뮬레이션 진행 중 기록된 15분 단위 활동 및 VA 제어 기억 내역
- `3_interaction_history.xlsx`: 환경, 가구원 정보, `Hourly/Quarterly Activity`, 상세한 `Concrete Action`, `Latent Command` 및 LLM 평가 결과(Rating/Reason) 추출

## 4. 주요 파일/폴더

- 진입점: `main.py`
- 설정: `config.yaml`
- 스키마: `src/schema.py`
- 생성/시뮬/평가/추출:
  - `src/generator.py`
  - `src/simulator.py`
  - `src/evaluator.py`
  - `src/exporter.py`
- 데이터 출력:
  - `data/generated/environments/`
  - `data/generated/families/`
  - `data/logs/`
  - `data/exports/run_<id>/`

## 5. 참고

- `data/templates/home.json`은 A~D 타입 시드 파일입니다.
- 이 파일이 없으면 `~/Desktop/home.json`을 fallback으로 사용합니다.
