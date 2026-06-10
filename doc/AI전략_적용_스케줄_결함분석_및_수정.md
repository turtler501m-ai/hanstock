# AI 전략 / 적용 / 스케줄 결함 분석 및 수정

작성일: 2026-06-10

## 0. 요약

`전략탭_구현진행현황.md`는 구현률을 "약 95%"로 평가한다. 그러나 그 95%는
**AI 전략을 저장·관리·검증·기록하는 관리 레이어** 기준이며, 정작
**"사용자가 만든 전략이 실제 매매 판단(후보 스코어링)을 바꾸는"** 적용 레이어는
코드상 사실상 동작하지 않았다.

이 문서는 (1) 발견된 결함을 코드 근거와 함께 정리하고, (2) 이번에 적용한 수정
내용을 파일별로 기록하며, (3) 동작 변화와 남은 과제를 정리한다.

---

## 1. 발견된 결함

### 1.1 [적용] 전략 profile이 스코어링에 0% 반영

`ai_strategies` 테이블/JSON에는 `strategy_type`, `risk_level`, `focus`, `avoid`,
`min_ai_confidence`, `min_rule_score_for_ai`, `allow_candidate_promotion`,
`ai_weight` 등 풍부한 profile이 저장된다(`src/db/repository.py:788` `_default_strategy_profile`).
그러나 이 profile은 **저장만 되고 실제 스코어링 경로로 전달되지 않았다.**

- `src/strategy/predict.py` — `ModelPredictor.__init__()`이 인자를 받지 않고
  `config`에서만 값을 읽었다. 선택된 전략의 profile을 전혀 알지 못했다.
- `src/strategy/seven_split.py` — `find_candidates(...)`는 전략 정보로
  `strategy_model`(문자열) 하나만 받았고, `ModelPredictor()`를 인자 없이 생성했다.
- `src/dashboard/core.py` — `_compute_candidates`가 `selected_strat`의 profile을
  읽고도 `build_dashboard_candidates`에는 `strategy_model`만 넘겼다.

### 1.2 [적용] OpenAI 프롬프트가 고정 문자열

`predict.py`의 `_predict_probability()`가 보내는 `instructions`는 하드코딩된
고정 문자열이었다. "단기 공격형"이든 "보수 반등형"이든 OpenAI로 가는 프롬프트가
동일했으므로, 전략 설명/성격이 결과에 영향을 주지 못했다.

### 1.3 [적용] 캐시 키에 전략 정보 없음

`predict.py`의 `_cache_key()`가 feature 값만으로 키를 만들었다. 전략을 바꿔도
feature가 같으면 캐시된 동일 점수를 반환했다 → "전략을 바꿔도 결과가 안 바뀌는"
직접 원인.

### 1.4 [적용] profile의 후보 정책 필드가 미사용

`min_rule_score_for_ai`(약한 후보에 AI 비용 낭비 방지)와
`allow_candidate_promotion`(룰 점수는 낮아도 AI 고평가 종목 승격)이 후보 선정
로직 어디에도 연결되어 있지 않았다. 또한 AI가 점수를 내려 기준 미달이 된 종목도
후보 목록에 그대로 남았다.

### 1.5 [스케줄] 대시보드 수동 실행이 전략을 강제하지 못함 + 기록 불일치

- `POST /api/scheduler/run`(`stock.py`)이 `strategy_id`를 받지 않았다.
- 결과는 항상 `strategy_id="seven_split"`로 기록되어, 실제로 선택된 전략과
  기록이 어긋났다(`scheduler.py` `run_scheduled_cycle`).

### 1.6 [스케줄] GitHub Actions의 mode가 무시됨

- `mode` 입력을 정의해놓고 실행 스텝(`python -m src.trader`)에 **전달하지 않았다.**
  `trader.py`의 `__main__`은 `run()`을 인자 없이 호출하므로 mode가 무의미했다.
- (참고) 이 워크플로에 정기 `schedule:` cron이 없는 것은 결함이 아니다. 정기
  자동매매는 GCP VM crontab이 전담하며, Actions는 수동 실행 보조용이다. 자세한
  배경은 `2.6` 참조.

---

## 2. 적용한 수정

### 2.1 `src/strategy/predict.py`

- `ModelPredictor(strategy_profile=None, description="")`로 시그니처 확장(기본값
  유지 → 기존 호출 호환).
- profile에서 다음을 추출:
  - `ai_weight`(상한 `risk.max_ai_weight` 적용) → `score_weight`
  - `min_ai_confidence` → `min_confidence`
  - `strategy_type`, `risk_level`, `focus`, `avoid`
  - `min_rule_score_for_ai`, `allow_candidate_promotion`(후보 선정 단계에서 참조)
- `_build_strategy_signature()` 추가: 전략 성격 해시(16자)를 생성.
- `_strategy_instructions()` 추가: `strategy_type`/`risk_level`/`focus`/`avoid`/
  `description`을 OpenAI `instructions`에 동적으로 반영.
- `_cache_key()`에 `strategy_signature` 포함 → 전략이 다르면 캐시도 분리.

### 2.2 `src/strategy/seven_split.py`

- `find_candidates(..., strategy_profile=None, strategy_description="")`로 확장.
- 전략 정보가 비어 있으면 active 전략의 `profile`/`description`까지 자동 로드
  (기존엔 model만 로드).
- `ModelPredictor(strategy_profile=..., description=...)`로 생성.
- AI 평가 대상 선정에 `min_rule_score_for_ai` 필터 적용(두 스캔 경로 모두).
- `_apply_ai_promotion()` 헬퍼 추가:
  - `allow_candidate_promotion=True`면 룰 미달이라도 AI 최종 점수가 기준 이상인
    종목을 후보로 승격(`promoted_by_ai` 표시).
  - AI 평가 결과 기준 미달이 된 기존 후보는 제거.

### 2.3 `src/dashboard/core.py`

- `build_dashboard_candidates(..., strategy_profile=None, strategy_description="")`로
  확장하고 두 `find_candidates` 호출에 전달.
- `_compute_candidates`가 `selected_strat`의 `profile`/`description`을 추출해
  `build_dashboard_candidates`까지 전달.
- `_scheduler_run_state`에 `strategy_id` 키 추가.

### 2.4 `src/dashboard/routes/stock.py`

- 전략 검증 API(`POST /api/ai-strategies/{id}/verify`)가 전략 profile/description으로
  `ModelPredictor`를 생성하도록 변경 → 검증이 실제 전략 프롬프트를 사용.
- `POST /api/scheduler/run`이 `strategy_id`를 받고, 없으면 선택된 전략으로 채워
  `force_strategy_id`로 전달. 응답에 `strategy_id` 포함.

### 2.5 `src/scheduler.py`

- `run_scheduled_cycle`에서 `force_strategy_id`가 None이면(예: cron 경로) 선택된
  전략 model로 채워, trader 실행과 결과 기록의 `strategy_id`를 일치시킴.

### 2.6 `.github/workflows/auto_trade.yml`

- `mode` 입력 옵션을 `execute`/`analysis_only`로 정리.
- 실행 스텝을 `python -m src.scheduler --mode "$SCHEDULE_MODE"`로 변경하여
  mode가 실제로 반영되도록 함.
- **`schedule:` cron은 의도적으로 추가하지 않는다.** 정기 자동매매는 이미 GCP VM
  crontab(`scripts/vm/install-daily-auto-cron.sh`, 평일 KST 09–15시)이 담당하며,
  여기에 같은 시간대 cron을 두면 매매 사이클이 이중 실행되어 중복 주문 위험이
  있다. 따라서 이 워크플로는 수동(`workflow_dispatch`) 전용으로 유지한다.
  (초안에서는 `'0 0-6 * * 1-5'` cron 추가를 검토했으나 위 이유로 철회했다.)

### 2.7 `src/trader.py`

- `build_runtime_plan`의 실제 매매 스캔 경로에서 active 전략의
  `profile`/`description`을 추출해 `find_candidates(...)`에 `strategy_profile`/
  `strategy_description`으로 전달하도록 수정.
- 이 변경이 없으면 신규 인자의 기본값(None/"") 때문에 trader는 깨지지 않지만
  **전략 profile이 실제 자동매매 경로에 적용되지 않고** 대시보드 미리보기에서만
  적용된다. 즉 `2.1`~`2.3`의 효과를 실매매까지 연결하는 필수 배선이다.

---

## 3. 동작 변화 (Before → After)

| 항목 | Before | After |
|---|---|---|
| 전략 설명/성격 | OpenAI 프롬프트에 미반영 | `instructions`에 동적 반영 |
| 전략 변경 시 캐시 | 동일 feature면 동일 결과 | `strategy_signature`로 분리 |
| `min_rule_score_for_ai` | 미사용 | AI 평가 대상 필터로 적용 |
| `allow_candidate_promotion` | 미사용 | 후보 승격/강등 로직으로 적용 |
| 스케줄러 실행 전략 | 강제 불가, 기록 불일치 | `strategy_id` 강제 + 기록 일치 |
| GitHub Actions | 수동 실행만, mode 무시 | 수동 실행 + mode 반영(정기 cron은 VM crontab이 전담, 이중 실행 방지 위해 미추가) |

---

## 4. 호환성

- `ModelPredictor()`, `find_candidates(...)`, `build_dashboard_candidates(...)`의
  신규 인자는 모두 기본값을 가지므로 기존 호출부(`plunge_bounce.py`,
  `train_lgbm` 등)는 변경 없이 동작한다.
- 단, 실제 자동매매 경로인 `trader.py`는 기본값으로 두면 깨지지는 않으나 전략
  profile이 적용되지 않으므로, `2.7`에서 명시적으로 profile/description을 넘기도록
  배선했다(기본값 호환성은 유지되나 적용 효과를 위해 호출부를 갱신한 케이스).
- 전략을 선택하지 않은 경우 기존과 동일하게 config 기본값으로 폴백한다.

---

## 5. 점검 결과 (멀티 에이전트)

테스트 실행과 코드 리뷰를 두 에이전트로 병렬 수행했다.

**테스트** — 관련 스위트 전부 통과(최종 47/47 OK).
- `test_strategy_ai`, `test_ai_strategy_presets`, `test_ai_strategy_lifecycle`
- `test_scheduler_api`, `test_scheduler_modes`
- `test_trader_presets`, `test_trader_core`, `test_dashboard_core`
- `test_scanned_candidates_persistence`, `test_dashboard_plan_views`
- 초기에 `test_trader_presets`의 2건이 `find_candidates` 옛 시그니처를 단언해 실패 →
  새 인자(`strategy_profile`, `strategy_description`)를 기대값에 반영해 통과.

**코드 리뷰** — BLOCKING 없음. 핵심 경로(전략별 캐시 분리, candidates/scan_summary
dict 객체 공유로 in-place 갱신 전파, 승격/강등, `ThreadPoolExecutor` 0-워커 가드,
cron/mode 배선) 정상 확인. 지적된 견고성 항목 3건을 반영:
- `predict.py`: `min_rule_score_for_ai`/`min_confidence` float 변환 방어(`_as_float`),
  `focus`/`avoid`가 문자열일 때 문자 단위로 분해되는 문제 방어(`_as_str_list`).
- `stock.py`: 선택 전략 model이 `"none"`(룰 전용)일 때 `scheduler.py`와 동일하게
  `force_strategy_id`를 None으로 유지하여 기록을 `seven_split`로 일관 폴백.

## 6. 남은 과제

- `min_rule_score_for_ai`/`allow_candidate_promotion`을 전략 등록/수정 UI에서
  직접 편집할 수 있게 노출(현재는 profile 기본값/JSON 의존).
- 대시보드에서 cron 스케줄 **시각 자체**를 편집하는 UI(현재는 VM `crontab` 또는
  Actions cron 수정 필요).
- 승격(`promoted_by_ai`) 종목을 후보 테이블/상세 UI에서 시각적으로 구분.
- 백테스트 기반 검증(현재 검증은 단건 호출 성공 여부 중심).
