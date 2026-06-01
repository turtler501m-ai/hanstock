# AI 전략 탭 현황 및 개선사항 정리

작성일: 2026-06-01

## 1. 목적

이 문서는 대시보드의 `AI 전략` 탭이 현재 어떤 기능을 제공하는지, 이미 반영된 수정/개선사항이 무엇인지, 그리고 추가로 개선해야 할 항목을 정리한다.

관련 주요 파일:

- `web/templates/index.html`: AI 전략 탭 화면, 신호/계획 탭의 AI 랭커 선택 UI
- `web/static/js/app.js`: AI 전략 목록 조회, 선택, 검증, 등록, 후보 찾기 연동
- `src/dashboard/routes/stock.py`: AI 전략 API
- `src/dashboard/core.py`: 후보 탐색 API와 전략 파라미터 반영
- `src/db/repository.py`: AI 전략 DB/JSON 저장
- `src/strategy/predict.py`: OpenAI 기반 AI 점수 계산
- `src/strategy/seven_split.py`: 룰 기반 점수, 후보 스캔, AI 점수 결합

## 2. 현재 반영된 수정/개선사항

### 2.1 AI 전략 전용 탭 추가

대시보드에 `AI 전략` 탭이 존재하며, 현재 사용 가능한 전략과 사용자가 추가한 전략을 목록으로 보여준다.

현재 제공 기능:

- 전략 목록 조회
- 전략 선택 체크박스
- 전략별 검증 버튼
- 선택 전략 적용 및 후보 찾기 실행
- 신규 AI 전략 등록 폼

### 2.2 AI 전략 저장 구조 추가

AI 전략은 `ai_strategies` 테이블에 저장된다. JSON 백업 파일도 `.runtime/ai_strategies.json`에 저장된다.

저장 필드:

- `id`
- `name`
- `provider`
- `model`
- `weight`
- `description`
- `selected`

기본 전략도 함께 제공된다.

- GPT-5-mini 기본 추론 랭커
- 기본 기술 룰베이스 랭커
- LightGBM 순위 예측 랭커
- 리스크 예산 배분기
- PPO 강화학습 최적 정책

### 2.3 신규 전략 등록 기능

사용자는 화면에서 다음 값을 입력해 신규 전략을 등록할 수 있다.

- 전략 이름
- 대상 AI 모델
- AI 가중치
- 전략 상세 설명

등록된 전략은 DB와 JSON 백업에 저장되고, 이후 목록과 후보 선정 랭커 드롭다운에 노출된다.

### 2.4 전략 선택 상태 저장

AI 전략 목록에서 체크박스를 변경하면 `/api/ai-strategies/{id}/select` API를 통해 선택 상태가 저장된다.

선택된 전략은 `신호/계획` 탭의 `후보 선정 AI 랭커` 드롭다운에 반영된다.

### 2.5 전략 검증 API 추가

각 전략에는 검증 버튼이 있다.

현재 동작:

- `provider`가 `none`이면 로컬 룰 기반 전략으로 보고 즉시 성공 처리한다.
- OpenAI 전략이면 샘플 feature payload를 만들어 `ModelPredictor`로 테스트 호출한다.
- API 키 누락, 호출 실패, fallback 발생 시 실패 메시지를 표시한다.

### 2.6 후보 찾기 흐름과 AI 전략 연결

`AI 전략` 탭에서 선택 전략 적용을 누르면:

1. AI 전략 목록을 다시 읽는다.
2. 선택된 전략 중 첫 번째 전략을 `select-ai-ranker`에 반영한다.
3. `신호/계획` 탭으로 이동한다.
4. 신규 매수 후보 찾기(`renderCandidates`)를 실행한다.

후보 찾기 API(`/api/candidates`)는 선택된 전략의 `model`, `weight`, `provider`를 읽어 후보 스캔에 반영한다.

### 2.7 OpenAI 점수와 룰 점수 결합

`ModelPredictor`는 기술적 룰 점수와 OpenAI 예측 점수를 가중 평균한다.

현재 계산 구조:

- 룰 점수: 0~5점 스케일
- OpenAI 확률: 0.0~1.0
- OpenAI 확률을 0~5점으로 변환
- 최종 점수 = 룰 점수 * (1 - AI 가중치) + AI 점수 * AI 가중치

기본 AI 가중치는 `0.4`이다.

### 2.8 OpenAI 호출 캐시와 토큰 사용량 추적

OpenAI 예측 결과는 `.runtime/openai_ai_cache.json`에 캐시된다.

또한 응답 usage 정보를 기반으로 토큰 사용량을 DB/JSON에 기록하는 로직이 있다.

## 3. 현재 구조상 한계

### 3.1 전략 설명이 실제 판단에 반영되지 않음

신규 전략 등록 시 `description`을 입력하지만, 현재 OpenAI 프롬프트에는 이 설명이 포함되지 않는다.

결과적으로 아래처럼 전략 설명을 다르게 작성해도 실제 스코어링 결과는 달라지지 않는다.

- 단기 공격형 전략
- 보수적 저변동성 전략
- 낙폭 과대 반등 전략
- 거래량 급증 추세 추종 전략

현재 실제로 영향을 주는 값은 주로 `model`과 `weight`이다.

### 3.2 다중 선택처럼 보이지만 실제 적용은 단일 전략 중심

AI 전략 탭은 체크박스 기반이라 여러 전략을 선택할 수 있다.

하지만 `선택 전략 적용 및 찾기`는 선택된 전략 중 첫 번째 전략만 `신호/계획` 탭의 랭커로 지정한다.

즉 현재 UI는 다중 전략 앙상블을 암시하지만, 실제 구현은 단일 랭커 선택에 가깝다.

### 3.3 로컬 모델 전략의 실체가 불명확함

기본 목록에는 LightGBM, PPO, 리스크 예산 배분기 같은 전략이 존재한다.

그러나 현재 검증 API에서는 `provider: none`이면 실제 모델 로딩이나 추론 없이 성공으로 처리한다.

따라서 화면상으로는 모델 전략처럼 보이지만, 실제 후보 스캔에 반영되는지는 전략별로 명확하지 않다.

### 3.4 AI 점수가 후보를 새로 승격시키는 구조가 제한적임

현재 후보 선정은 먼저 룰 기반 점수로 후보를 고른 뒤, 상위 일부 후보에 AI 점수를 반영하는 구조에 가깝다.

이 구조에서는 룰 점수가 낮지만 AI가 높게 평가할 수 있는 종목이 후보군에 들어오기 어렵다.

### 3.5 캐시 키와 전략 정보의 결합이 부족함

후보 캐시에는 랭커와 optimizer가 포함되지만, 전략 설명이나 전략 버전 같은 세부 정보는 충분히 반영되지 않는다.

추후 전략 설명을 프롬프트에 반영하면 캐시 키에도 전략 설명 또는 전략 버전이 포함되어야 한다.

### 3.6 삭제/수정 기능이 없음

현재 신규 전략은 추가할 수 있지만, 등록된 전략을 수정하거나 삭제하는 UI/API가 없다.

잘못 등록한 전략이 누적되면 운영성이 떨어진다.

### 3.7 검증 기준이 운영 품질을 보장하지 않음

현재 검증은 샘플 feature payload 1건에 대한 호출 성공 여부에 가깝다.

실제 전략 품질을 판단하려면 다음 검증이 필요하다.

- 최근 N일 백테스트
- 후보 선정 결과 비교
- 룰 점수 대비 성능 개선 여부
- 과도한 매수 후보 생성 여부
- 토큰 비용 추정
- API 장애 시 fallback 동작 확인

### 3.8 UI 문구와 실제 기능 사이의 기대치 차이

현재 UI 문구는 “전략 신설”, “선택 전략 적용”, “실시간 바인딩”처럼 강한 표현을 사용한다.

하지만 실제 기능은 전략 파라미터를 저장하고 후보 탐색에 일부 반영하는 수준이다.

사용자가 전략별 독립 로직이나 멀티 전략 합의를 기대할 수 있으므로 문구 조정 또는 기능 보강이 필요하다.

## 4. 추가 개선 제안

### 4.1 전략 설명을 OpenAI 프롬프트에 반영

신규 전략의 `description`을 실제 OpenAI 요청에 포함한다.

예시:

- 공격형: 변동성과 거래량 증가를 더 높게 평가
- 보수형: 낙폭, 변동성, 과열 RSI를 더 엄격하게 평가
- 반등형: RSI2, 볼린저 하단 근접, 단기 낙폭을 우선 평가

필요 작업:

- `ModelPredictor.predict()` 또는 생성자에 strategy context 전달
- `/api/candidates`에서 선택 전략의 description 전달
- 캐시 키에 strategy id/version/description hash 반영
- 테스트 추가

우선순위: 높음

### 4.2 다중 선택 정책 명확화

두 가지 방향 중 하나를 선택해야 한다.

방향 A: 단일 전략 선택으로 단순화

- 체크박스를 라디오 버튼 또는 단일 select로 변경
- “선택 전략 적용” 문구를 “현재 전략으로 후보 찾기”로 변경
- 구현 난이도 낮음

방향 B: 실제 다중 전략 앙상블 구현

- 여러 전략의 점수를 각각 계산
- 평균, 가중 평균, 최소 합의, 최대 합의 중 정책 선택
- 전략별 근거와 최종 합의 점수 표시
- 구현 난이도 중간 이상

추천: 우선 단일 전략 선택으로 UX를 정리하고, 이후 앙상블을 별도 기능으로 추가한다.

우선순위: 높음

### 4.3 전략 수정/삭제 기능 추가

운영 편의성을 위해 다음 API와 UI가 필요하다.

- `PATCH /api/ai-strategies/{id}`: 이름, 모델, 가중치, 설명 수정
- `DELETE /api/ai-strategies/{id}`: 사용자 추가 전략 삭제
- 기본 전략은 삭제 방지 또는 복구 기능 제공

우선순위: 중간

### 4.4 로컬 모델 전략 provider 분리

현재 `provider: none`은 룰 기반과 로컬 모델을 모두 섞어서 표현한다.

추천 provider:

- `rule`: 순수 룰 기반
- `openai`: OpenAI Responses API
- `lightgbm`: LightGBM 로컬 모델
- `ppo`: 강화학습 정책 모델
- `allocator`: 포트폴리오 배분 로직

이렇게 분리하면 검증, 표시, 실행 흐름을 명확히 나눌 수 있다.

우선순위: 중간

### 4.5 전략 검증을 백테스트 기반으로 강화

현재 검증은 API 연결 테스트에 가깝다.

개선된 검증 결과에는 다음 항목을 표시한다.

- 최근 스캔 대상 수
- 후보 선정 수
- 평균 최종 점수
- 룰 점수 대비 상승/하락 종목 수
- API 호출 수와 예상 토큰 비용
- fallback 발생 여부
- 최근 N일 단순 성과 비교

우선순위: 중간

### 4.6 AI 후보 승격 구조 개선

현재는 룰 점수 기준으로 먼저 필터링하는 성격이 강하다.

개선 방향:

1. 전체 스캔 대상에 룰 점수를 계산한다.
2. 룰 점수 상위 N개와 관심종목 전체를 AI 평가 대상으로 만든다.
3. AI 최종 점수 기준으로 후보를 재정렬한다.
4. 최종 점수가 기준 이상이면 룰 점수가 낮아도 후보로 승격할 수 있게 한다.

주의:

- 비용 관리를 위해 `AI_CANDIDATE_LIMIT`은 반드시 유지해야 한다.
- OpenAI API 실패 시 기존 룰 기반 후보 선정으로 fallback해야 한다.

우선순위: 높음

### 4.7 전략별 결과 설명 강화

후보 테이블과 상세 모달에 다음 정보를 추가하면 판단 신뢰도가 올라간다.

- 룰 점수
- AI 점수
- 최종 점수
- AI 가중치
- 적용 전략명
- 모델 상태
- fallback 사유
- 상위 기여 feature

현재 일부 데이터는 이미 payload에 존재하므로 UI 표시를 보강하면 된다.

우선순위: 중간

### 4.8 캐시 무효화 정책 개선

전략이 변경되면 기존 후보 캐시가 잘못 재사용될 수 있다.

캐시 signature에 다음 값을 포함하는 것이 좋다.

- strategy id
- strategy model
- strategy weight
- strategy description hash
- strategy updated_at 또는 version
- AI 활성화 여부
- API 키 설정 여부
- candidate limit

우선순위: 중간

### 4.9 전략 변경 이력 저장

실거래 또는 승인 흐름과 연결되는 시스템이므로 전략 변경 이력을 남기는 것이 좋다.

기록 대상:

- 전략 생성/수정/삭제
- 선택 상태 변경
- 검증 결과
- 후보 찾기에 사용된 전략 id/model/weight

우선순위: 낮음~중간

### 4.10 안전장치 강화

AI 전략이 실제 주문 승인 대기열까지 연결될 수 있으므로 다음 제한이 필요하다.

- AI 전략 변경 후 첫 실행은 `DRY_RUN=true` 권장 표시
- `ENABLE_LIVE_TRADING=true` 상태에서는 전략 변경 경고
- 검증 실패 전략은 후보 찾기 적용 제한 옵션
- fallback 상태에서 주문 대기열 생성 여부 명확히 표시

우선순위: 높음

## 5. 권장 작업 순서

1. UI 정책 정리: 단일 전략 선택으로 정리하거나 실제 앙상블 구현 방향 결정
2. 전략 설명을 OpenAI 프롬프트와 캐시 키에 반영
3. AI 후보 승격 구조 개선
4. 전략 수정/삭제 API와 UI 추가
5. provider 분리로 룰/OpenAI/LightGBM/PPO 구분
6. 백테스트 기반 검증 기능 추가
7. 후보 상세 UI에 룰 점수, AI 점수, 최종 점수, fallback 사유 표시
8. 전략 변경 이력과 안전장치 추가

## 6. 단기 구현 추천안

가장 먼저 적용할 단기 개선 조합은 다음과 같다.

### 6.1 단일 전략 선택 UI로 정리

현재 다중 체크박스는 실제 동작과 다르므로 단일 선택으로 바꾸는 것이 좋다.

효과:

- 사용자 혼동 감소
- 구현 복잡도 낮음
- 현재 API 구조를 크게 바꾸지 않아도 됨

### 6.2 전략 설명 프롬프트 반영

신규 전략 등록의 실질적 의미를 만들려면 description을 OpenAI 판단 기준으로 반영해야 한다.

효과:

- 사용자가 만든 전략마다 실제 결과 차이가 생김
- AI 전략 탭의 존재 이유가 명확해짐

### 6.3 후보 상세 근거 표시 보강

이미 존재하는 `rule_score`, `ml_score`, `final_score`, `ai_model_status`, `ai_fallback_reason`을 UI에 더 명확히 표시한다.

효과:

- AI가 왜 후보를 올렸는지 확인 가능
- fallback 여부를 사용자가 즉시 파악 가능

## 7. 결론

현재 `AI 전략` 탭은 전략 목록 관리, 선택 상태 저장, OpenAI 가중치 기반 후보 탐색 연동까지는 구현되어 있다.

다만 현재 구조는 “전략을 직접 설계하고 여러 전략을 적용한다”는 화면 기대치에 비해 실제 엔진 반영 범위가 제한적이다. 특히 전략 설명 미반영, 다중 선택과 단일 적용의 불일치, 로컬 모델 전략 검증 부재는 우선 개선 대상이다.

단기적으로는 단일 전략 선택 UX 정리, 전략 설명의 프롬프트 반영, 후보 상세 점수 표시 강화를 먼저 적용하는 것이 가장 효과적이다.

## 8. 인터넷 자료 기반 AI 전략 설정 추가안

아래 설정안은 NIST AI Risk Management Framework, FINRA 알고리즘 트레이딩 통제 가이드, QuantConnect 백테스트/워크포워드 문서, OpenAI Structured Outputs 문서를 참고해 현재 프로젝트에 맞게 적용 가능한 형태로 정리한 것이다.

### 8.1 전략 설정 화면에 추가할 권장 필드

AI 전략 등록/수정 화면에 다음 필드를 추가하는 것이 좋다.

| 필드 | 권장 기본값 | 목적 |
| --- | --- | --- |
| `strategy_type` | `rebound` | 전략 성격 구분. 예: 반등형, 추세형, 보수형, 변동성 회피형 |
| `risk_level` | `balanced` | 공격/중립/보수 설정 |
| `max_ai_weight` | `0.4` | AI 점수가 룰 점수를 과도하게 덮어쓰지 않도록 제한 |
| `min_rule_score_for_ai` | `1.5` | 너무 약한 후보에 AI 비용을 쓰지 않도록 1차 필터 |
| `ai_candidate_limit` | `5` | OpenAI 호출 비용과 지연시간 제한 |
| `min_ai_confidence` | `0.60` | 낮은 확신의 AI 결과는 참고값으로만 사용 |
| `require_backtest_pass` | `true` | 검증 실패 전략의 실전 적용 제한 |
| `allow_candidate_promotion` | `false` | AI 점수로 룰 미달 종목을 후보 승격할지 여부 |
| `max_position_weight` | 기존 `MAX_SINGLE_WEIGHT` 사용 | 단일 종목 집중 방지 |
| `cooldown_minutes` | `30` | 같은 전략의 과도한 재실행 방지 |

단기 권장값:

- 보수 운영: `max_ai_weight=0.25`, `min_ai_confidence=0.70`, `allow_candidate_promotion=false`
- 균형 운영: `max_ai_weight=0.40`, `min_ai_confidence=0.60`, `allow_candidate_promotion=false`
- 실험 운영: `max_ai_weight=0.50`, `min_ai_confidence=0.55`, `allow_candidate_promotion=true`, 단 `DRY_RUN=true` 필수

### 8.2 전략 유형별 프롬프트 설정

전략 설명을 단순 자유 텍스트로만 저장하지 말고, 구조화된 전략 프로필로 분리하는 것이 좋다.

예시 설정:

```json
{
  "strategy_type": "rebound",
  "risk_level": "balanced",
  "focus": ["rsi2_oversold", "bollinger_lower_band", "volume_recovery"],
  "avoid": ["high_volatility_breakdown", "overheated_rsi", "weak_liquidity"],
  "time_horizon": "short_term",
  "max_ai_weight": 0.4,
  "min_ai_confidence": 0.6
}
```

OpenAI 호출에는 이 프로필을 함께 전달하고, 응답은 JSON Schema로 고정한다.

권장 응답 필드:

- `probability`: 0.0~1.0 매수 품질 확률
- `confidence`: 0.0~1.0 모델 확신도
- `risk_flags`: 위험 요인 배열
- `rationale`: 짧은 판단 근거
- `recommended_action`: `buy`, `watch`, `reject`

이 방식은 OpenAI Structured Outputs 권장 방식과 맞고, 프론트에서 안정적으로 결과를 표시하기 쉽다.

### 8.3 백테스트 및 검증 설정

QuantConnect 문서의 백테스트/워크포워드 원칙을 현재 프로젝트에 적용하면 다음 검증 설정이 적절하다.

권장 검증 항목:

- 최근 6~12개월 데이터를 사용한 기본 백테스트
- 최근 구간 일부를 out-of-sample로 분리
- 전략 파라미터 변경 시 walk-forward 검증
- 수수료, 슬리피지, 체결 지연을 보수적으로 반영
- 후보 수, 거래 수, 승률, 손익비, 최대 낙폭을 함께 기록
- 실거래 전 paper trading 또는 `DRY_RUN=true` 기간을 둠

전략 검증 결과는 단순 성공/실패 대신 아래 형태로 저장하는 것이 좋다.

```json
{
  "backtest_pass": true,
  "period_days": 180,
  "candidate_count": 42,
  "trade_count": 18,
  "win_rate": 0.56,
  "max_drawdown_pct": -8.2,
  "avg_return_pct": 2.1,
  "overfit_risk": "medium",
  "notes": "Out-of-sample 성과가 in-sample 대비 70% 이상 유지됨"
}
```

### 8.4 리스크 통제 설정

FINRA의 알고리즘 트레이딩 통제 관점과 NIST AI RMF의 GOVERN/MAP/MEASURE/MANAGE 구조를 적용하면, AI 전략에는 최소한 다음 통제가 필요하다.

필수 통제:

- 전략 변경 이력 저장
- 검증 실패 전략의 실전 적용 제한
- API 장애 시 룰 기반 fallback
- 단일 종목 최대 비중 제한
- 일일 손실 한도 초과 시 후보 생성 또는 주문 생성 중단
- `ENABLE_LIVE_TRADING=true`일 때 전략 변경 경고
- AI 결과가 주문으로 이어질 때 승인 대기열을 거치도록 유지

현재 프로젝트 기본값과 맞춰 유지해야 할 안전 설정:

```text
DRY_RUN=true
TRADING_ENV=demo
ENABLE_LIVE_TRADING=false
REQUIRE_APPROVAL=true
```

### 8.5 비용 및 지연시간 설정

OpenAI 기반 전략은 비용과 지연시간 통제가 필요하다.

권장 설정:

- `AI_CANDIDATE_LIMIT=5` 기본 유지
- 캐시 TTL은 장중 변동성을 고려해 후보 스캔 캐시는 짧게, OpenAI feature 캐시는 feature hash 기준으로 재사용
- API timeout은 기존 `OPENAI_TIMEOUT_SECONDS=20` 유지
- API 실패 시 전체 후보 찾기를 실패시키지 말고 룰 기반 결과를 반환
- 토큰 사용량을 전략 id, 모델명, 날짜 단위로 집계

추가 DB 필드 후보:

- `last_verified_at`
- `last_used_at`
- `total_api_calls`
- `avg_latency_ms`
- `last_fallback_reason`
- `strategy_version`

### 8.6 추천 구현 우선순위

인터넷 자료를 반영한 추가 우선순위는 다음과 같다.

1. AI 전략 profile JSON 추가: `strategy_type`, `risk_level`, `focus`, `avoid`, `time_horizon`
2. OpenAI Structured Outputs 응답 스키마 강화: `probability`, `confidence`, `risk_flags`, `recommended_action`
3. 전략별 캐시 키에 `strategy_version`과 profile hash 반영
4. 전략 검증 API를 백테스트 요약 결과로 확장
5. 검증 실패 또는 fallback 전략의 실전 적용 제한
6. 전략 변경/검증/사용 이력 테이블 추가
7. AI 후보 승격 기능은 `DRY_RUN=true`에서만 먼저 허용

## 9. YouTube 및 GitHub 자료 기반 추가 분석

이번 추가 조사는 YouTube/YouTube Music에 공개된 영상 메타데이터, 영상 링크가 포함된 관련 페이지, 그리고 GitHub의 AI/알고리즘 트레이딩 오픈소스 저장소를 기준으로 정리했다.

주의할 점:

- YouTube 영상은 과장된 수익률, 단기 자동매매 홍보, 검증되지 않은 봇 판매 콘텐츠가 많다.
- 따라서 영상에서 얻을 수 있는 실무 포인트는 “수익률 주장”이 아니라 “검증 절차, 리스크 통제, 페이퍼 트레이딩, 거래일지, 전략 일관성” 중심으로만 반영하는 것이 안전하다.
- GitHub 저장소는 실제 구현 패턴을 확인하기 좋지만, 별 수나 README 문구만으로 실전 성능을 판단하면 안 된다.

### 9.1 YouTube 쪽에서 반복적으로 확인되는 설정 포인트

YouTube/팟캐스트형 영상 메타데이터에서 반복적으로 나타난 주제는 다음과 같다.

- 백테스트와 실전 성과는 다르므로 페이퍼 트레이딩 기간이 필요함
- 포지션 사이징은 감정이 아니라 사전 정의한 리스크 금액으로 계산해야 함
- 기대값, 손익비, 최대 손실, 거래 빈도를 함께 봐야 함
- 빠른 수익보다 생존 가능성과 일관성이 중요함
- 전략을 바꿀 때마다 거래일지와 성과 비교가 필요함
- 시장 급변 이벤트에서는 신호보다 리스크 제한과 현금 보유 판단이 중요할 수 있음

현재 프로젝트에 반영할 수 있는 UI 설정:

| 설정 | 권장값 | 반영 위치 |
| --- | --- | --- |
| `paper_trading_required_days` | `20` | 신규 AI 전략 실전 적용 전 최소 모의 운용 기간 |
| `max_risk_per_trade_pct` | `1.0` | 주문 수량 계산 또는 승인 대기열 표시 |
| `max_daily_ai_orders` | `3` | AI 전략 과다 주문 방지 |
| `require_trade_journal` | `true` | AI 전략 후보 생성/승인/거절 사유 기록 |
| `event_risk_mode` | `manual_only` | 금리, 실적, 급락장 등 이벤트 구간 자동 실행 제한 |

### 9.2 GitHub 저장소에서 확인한 구현 패턴

#### Lumibot

Lumibot은 AI trading team을 일반 백테스트/브로커 루프 안에서 실행하고, 실제 자금 연결 전에 의사결정, 주문, 산출물을 검토할 수 있게 하는 점이 중요하다.

현재 프로젝트 적용점:

- AI 전략 결과를 단순 점수로만 저장하지 말고 “판단 근거, 사용 feature, 모델 상태, 주문 생성 여부”를 함께 저장한다.
- AI 전략 탭에 `검증 산출물 보기` 또는 `최근 실행 근거` 링크를 추가한다.
- 실전 연결 전에 DRY_RUN/Paper 결과를 반드시 확인하는 플로우를 만든다.

#### ai-trader

ai-trader는 YAML 기반 config-driven 백테스트를 강조한다. 전략 클래스, 파라미터, 수수료, 데이터 기간, sizing을 설정 파일로 관리한다.

현재 프로젝트 적용점:

- AI 전략 설정을 DB row만으로 두지 말고 JSON profile로 버전 관리 가능하게 만든다.
- 전략별 backtest config를 생성해 재현 가능한 검증을 수행한다.
- `strategy_version`과 `profile_hash`를 저장해 같은 전략을 다시 검증할 수 있게 한다.

예시 profile:

```json
{
  "id": "gpt_rebound_balanced_v1",
  "strategy_type": "rebound",
  "risk_level": "balanced",
  "model": "gpt-5-mini",
  "ai_weight": 0.4,
  "sizer": {
    "type": "risk_percent",
    "risk_per_trade_pct": 1.0
  },
  "backtest": {
    "commission_bps": 15,
    "slippage_bps": 5,
    "min_warmup_periods": 60
  }
}
```

#### AgentQuant

AgentQuant는 LLM, agent 반복 횟수, 최소 Sharpe, warmup period, market impact, cache TTL을 설정으로 관리한다. 또한 시장 regime을 VIX percentile, momentum, SMA trend 등으로 구분한다.

현재 프로젝트 적용점:

- AI 전략 설정에 `market_regime_filter`를 추가한다.
- 최소 warmup 기간을 명시한다.
- market impact 또는 slippage bps를 전략 검증에 포함한다.
- AI 반복/재시도 횟수를 제한한다.

권장 추가 필드:

```json
{
  "min_warmup_periods": 60,
  "market_impact_bps": 5,
  "max_llm_retries": 1,
  "market_regime_filter": ["neutral", "bull", "low_volatility"]
}
```

#### VibeTrading

VibeTrading은 자연어 전략 생성 후 정적 검증, 백테스트, LLM 분석, 배포 순서를 둔다. 특히 정적 validator로 missing import, leverage, risk management 문제를 먼저 잡는 패턴이 유용하다.

현재 프로젝트 적용점:

- 신규 AI 전략 등록 시 description만 받지 말고 위험 설정 누락 여부를 검사한다.
- 레버리지, 손절, 최대 비중, 후보 승격 여부 같은 위험 필드가 없으면 경고한다.
- LLM 분석 결과를 바로 실행하지 않고 검증 리포트로 먼저 보여준다.

검증 체크리스트:

- 손절 또는 최대 손실 기준이 있는가
- 단일 종목 최대 비중이 있는가
- 실전 적용 전 DRY_RUN 조건이 있는가
- AI fallback 시 주문 생성 정책이 정의되어 있는가
- 전략 설명이 너무 모호하지 않은가

#### TradeSight

TradeSight는 self-hosted 전략 랩, AI 전략 토너먼트, 기술지표 백테스트, Alpaca paper trading, 웹 대시보드 패턴을 제공한다.

현재 프로젝트 적용점:

- 여러 AI 전략을 동시에 선택한다면 “동시 적용”보다 “전략 토너먼트/비교”로 먼저 구현하는 것이 안전하다.
- 전략별 후보 결과를 비교하고, 가장 안정적인 전략만 실제 후보 찾기 기본값으로 승격한다.
- 전략이 탈락/보류/승격되는 상태값을 둔다.

추천 상태값:

- `draft`: 등록됨, 아직 검증 전
- `verified`: 기본 검증 통과
- `paper_running`: 모의 운용 중
- `approved`: 기본 전략으로 사용 가능
- `retired`: 성능 저하 또는 사용자 중단

### 9.3 현재 프로젝트에 가장 유용한 결론

YouTube와 GitHub 자료를 함께 보면, AI 전략 탭은 “AI가 고른 종목을 바로 매수하는 화면”이 아니라 “전략을 생성, 검증, 비교, 승인, 운영 중단까지 관리하는 실험실”에 가까워야 한다.

따라서 현재 구조에 추가할 가장 실용적인 방향은 다음이다.

1. 전략 상태값 추가: `draft`, `verified`, `paper_running`, `approved`, `retired`
2. 전략 profile JSON 추가: 모델, 가중치, 리스크, 백테스트, regime filter 포함
3. 정적 검증 추가: 위험 설정 누락, 과도한 AI 가중치, 모호한 설명 감지
4. 백테스트 리포트 저장: 수익률보다 MDD, 거래 수, 승률, 손익비, slippage 반영 여부 중심
5. 페이퍼 트레이딩 기간 추가: 최소 20거래일 또는 N회 후보 생성 후 승인 가능
6. 전략 비교 화면 추가: 같은 기간에 여러 전략의 후보 결과를 비교
7. 기본 전략 승격 플로우 추가: 검증 통과 전략만 `신호/계획` 탭 기본 랭커로 지정 가능

### 9.4 추가 DB 스키마 후보

현재 `ai_strategies` 테이블에 다음 컬럼을 추가하는 것이 좋다.

```text
status TEXT DEFAULT 'draft'
profile_json TEXT
strategy_version INTEGER DEFAULT 1
profile_hash TEXT
last_verified_at TEXT
last_paper_started_at TEXT
last_paper_completed_at TEXT
last_used_at TEXT
last_validation_result TEXT
```

별도 이력 테이블도 권장한다.

```sql
CREATE TABLE IF NOT EXISTS ai_strategy_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    strategy_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload TEXT
);
```

이 테이블에는 생성, 수정, 검증, 후보 찾기 적용, fallback, paper trading 결과, 승인/중단 이벤트를 저장한다.

### 9.5 구현 우선순위 업데이트

기존 우선순위에 GitHub/YouTube 분석을 반영하면 다음 순서가 더 적절하다.

1. AI 전략 상태값과 profile JSON 추가
2. 전략 등록 시 정적 검증 추가
3. 단일 전략 선택 UX 정리
4. OpenAI Structured Outputs 응답 스키마 강화
5. 전략 설명/profile을 프롬프트와 캐시 키에 반영
6. 검증 API를 백테스트 리포트 중심으로 확장
7. paper trading 완료 전 실전 적용 제한
8. 여러 전략은 즉시 앙상블보다 비교/토너먼트 화면으로 먼저 제공
9. 승인된 전략만 `신호/계획` 기본 랭커로 승격
10. 전략 이벤트 이력 테이블 추가

## 10. 참고 출처

- NIST AI Risk Management Framework: https://www.nist.gov/itl/ai-risk-management-framework
- NIST AI RMF 1.0 문서: https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-ai-rmf-10
- FINRA Algorithmic Trading: https://www.finra.org/rules-guidance/key-topics/algorithmic-trading
- FINRA AI in the Securities Industry - Key Challenges: https://www.finra.org/rules-guidance/key-topics/fintech/report/artificial-intelligence-in-the-securities-industry/key-challenges
- QuantConnect Walk Forward Optimization: https://www.quantconnect.com/docs/v2/writing-algorithms/optimization/walk-forward-optimization
- QuantConnect Backtesting Getting Started: https://www.quantconnect.com/docs/v2/our-platform/backtesting/getting-started
- QuantConnect Trading and Orders: https://www.quantconnect.com/docs/v1/algorithm-reference/trading-and-orders
- OpenAI Structured Outputs: https://platform.openai.com/docs/guides/structured-outputs
- Lumibot GitHub: https://github.com/Lumiwealth/lumibot
- ai-trader GitHub: https://github.com/whchien/ai-trader
- AgentQuant GitHub: https://github.com/OnePunchMonk/AgentQuant
- VibeTrading GitHub: https://github.com/VibeTradingLabs/vibetrading
- TradeSight GitHub: https://github.com/rmbell09-lang/tradesight
- QuantLabs AI Trading Bots article with YouTube link: https://www.quantlabsnet.com/post/ai-trading-bots-build-backtest-automate-with-claude-ai-in-2026
- OVTLYR/TopPodcast YouTube trading plan and risk-management references: https://toppodcast.com/podcast_feeds/how-to-trade-stocks-and-options-podcast-with-ovtlyr-live/
