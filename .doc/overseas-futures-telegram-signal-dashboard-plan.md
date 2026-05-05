# 해외선물 텔레그램 매매신호 성과검증 대시보드 계획

## 목적

신규 AI 대시보드(`/ai-dashboard`)의 오른쪽 영역에 **해외선물 신호검증** 버튼을 추가하고, 텔레그램 채널/그룹에서 수집한 매매신호를 정규화하여 성과를 검증하는 별도 대시보드 흐름을 만든다.

이 기능은 기존 국내주식 자동매매 주문 흐름과 분리한다. 초기 목표는 자동 주문이 아니라 **신호 수집, 신호 해석, 진입/청산 검증, 승률/손익/리스크 분석**이다.

## UI 진입 방식

### 기존 화면 유지

- `/ai-dashboard`는 기존 AI 운영 대시보드로 유지한다.
- 오른쪽 상단 또는 오른쪽 사이드 패널에 `해외선물 신호검증` 버튼을 추가한다.
- 버튼 클릭 시 다음 중 하나로 이동한다.
  - 1차 권장: `/ai-dashboard/futures-signals`
  - 대안: `/futures-signals`

### 버튼 배치 권장안

```text
/ai-dashboard

상단/오른쪽 액션 영역
  [새로고침] [Kill Switch] [해외선물 신호검증]

또는 오른쪽 사이드 패널
  AI 운영 상태
  모델 상태
  감사 로그
  ------------------------------------------------
  [해외선물 신호검증 열기]
```

버튼은 기존 국내주식 자동매매와 혼동되지 않도록 색상과 라벨을 명확히 구분한다.

- 라벨: `해외선물 신호검증`
- 보조 문구: `Telegram signals / Backtest`
- 아이콘: `activity`, `chart-candlestick`, `message-circle` 중 하나

## 범위

### 1차 범위

- 텔레그램 메시지 수집
- 메시지 원문 저장
- 매매신호 파싱
- 종목, 방향, 진입가, 손절가, 목표가 추출
- 실제 시세 또는 캔들 데이터 기준 성과검증
- 대시보드에서 신호별 결과와 통계 확인

### 2차 범위

- 신호 제공자별 성과 비교
- 종목별 성과 비교
- 시간대별 성과 비교
- 리스크 기준 필터링
- 수동 검수/오파싱 수정 UI

### 제외 범위

- 초기 단계에서는 자동 주문을 하지 않는다.
- 국내주식 `trader.py`, 승인 큐, KIS 주문 흐름과 직접 연결하지 않는다.
- 검증 성능이 충분히 확인되기 전까지 실계좌 주문 기능은 추가하지 않는다.

## 전체 구조

```text
Telegram
  -> collector
  -> raw message store
  -> parser
  -> normalized signal table
  -> market data loader
  -> backtest / verification engine
  -> performance table
  -> FastAPI endpoints
  -> /ai-dashboard 오른쪽 버튼
  -> 해외선물 신호검증 대시보드
```

## 데이터 모델

### `telegram_messages`

텔레그램 원문 보관 테이블이다. 파싱 오류가 있어도 원문을 잃지 않는 것이 중요하다.

| 필드 | 설명 |
| --- | --- |
| `id` | 내부 ID |
| `telegram_message_id` | 텔레그램 메시지 ID |
| `channel_id` | 채널/그룹 ID |
| `channel_name` | 채널/그룹 이름 |
| `received_at` | 메시지 수신 시각 |
| `raw_text` | 메시지 원문 |
| `has_media` | 이미지/첨부 포함 여부 |
| `parse_status` | `pending`, `parsed`, `failed`, `ignored` |
| `parse_error` | 파싱 실패 사유 |
| `created_at` | 저장 시각 |

### `futures_signals`

정규화된 매매신호 테이블이다.

| 필드 | 설명 |
| --- | --- |
| `id` | 내부 신호 ID |
| `message_id` | `telegram_messages.id` |
| `provider` | 신호 제공자 |
| `symbol` | 예: `NQ`, `ES`, `GC`, `CL`, `YM`, `MNQ` |
| `exchange` | 예: `CME`, `COMEX`, `NYMEX` |
| `direction` | `long`, `short` |
| `entry_type` | `market`, `limit`, `range` |
| `entry_price` | 단일 진입가 |
| `entry_low` | 진입 범위 하단 |
| `entry_high` | 진입 범위 상단 |
| `stop_loss` | 손절가 |
| `take_profit_1` | 1차 목표가 |
| `take_profit_2` | 2차 목표가 |
| `take_profit_3` | 3차 목표가 |
| `signal_time` | 신호 발생 시각 |
| `status` | `open`, `closed`, `expired`, `invalid` |
| `confidence` | 파싱 신뢰도 |
| `raw_payload_json` | 파싱 결과 원본 JSON |

### `futures_signal_results`

성과검증 결과 테이블이다.

| 필드 | 설명 |
| --- | --- |
| `id` | 내부 결과 ID |
| `signal_id` | `futures_signals.id` |
| `verification_status` | `pending`, `hit_tp`, `hit_sl`, `expired`, `ambiguous` |
| `entry_filled_at` | 진입 체결 추정 시각 |
| `exit_at` | 청산 추정 시각 |
| `exit_reason` | `tp1`, `tp2`, `tp3`, `sl`, `timeout`, `manual` |
| `entry_fill_price` | 체결 추정 진입가 |
| `exit_price` | 청산가 |
| `pnl_points` | 포인트 손익 |
| `pnl_amount` | 계약 승수 반영 손익 |
| `max_favorable_excursion` | 최대 유리 이동 |
| `max_adverse_excursion` | 최대 불리 이동 |
| `holding_minutes` | 보유 시간 |
| `verified_at` | 검증 시각 |

## 텔레그램 수집 방식

### 권장 라이브러리

- `Telethon` 또는 `Pyrogram`
- 초기 구현은 `Telethon` 권장

### 필요한 환경변수

```text
TELEGRAM_API_ID=
TELEGRAM_API_HASH=
TELEGRAM_SESSION_NAME=
TELEGRAM_TARGET_CHANNELS=
```

`TELEGRAM_TARGET_CHANNELS`는 콤마 구분 문자열로 시작하고, 이후 설정 화면에서 관리 가능하게 확장한다.

### 수집 정책

- 메시지는 원문 그대로 먼저 저장한다.
- 중복 방지를 위해 `channel_id + telegram_message_id`에 unique constraint를 둔다.
- 수집기는 대시보드 서버와 분리 가능한 배치/백그라운드 작업으로 둔다.
- 텔레그램 세션 파일은 `.runtime` 또는 `data/private` 하위에 저장하고 git에 포함하지 않는다.

## 신호 파싱 규칙

### 파싱 대상 예시

```text
NQ long 18320
SL 18280
TP 18370 / 18420
```

```text
Gold sell 2345-2348
stop 2353
target 2338 2330
```

```text
MNQ 매수 18320 진입
손절 18280
1차 18360 2차 18410
```

### 정규화 규칙

- 종목명 alias를 표준 symbol로 변환한다.
  - `Nasdaq`, `NQ`, `USTEC`, `나스닥` -> `NQ`
  - `MNQ`, `마이크로나스닥` -> `MNQ`
  - `Gold`, `XAU`, `골드` -> `GC`
  - `Oil`, `WTI`, `크루드오일` -> `CL`
- 방향 alias를 표준 direction으로 변환한다.
  - `buy`, `long`, `매수`, `롱` -> `long`
  - `sell`, `short`, `매도`, `숏` -> `short`
- 진입가는 단일가 또는 범위로 저장한다.
- TP는 최대 3개까지 우선 저장하고, 추가 목표가는 JSON payload에 보존한다.
- 파싱 신뢰도가 낮으면 `parse_status=failed`가 아니라 `parsed` + `confidence 낮음`으로 저장한 뒤 수동 검수 대상에 올린다.

## 성과검증 기준

### 기본 체결 가정

- 신호 발생 이후 지정된 검증 기간 안에 entry 가격에 도달하면 체결로 본다.
- long:
  - low <= entry <= high 이면 진입 체결
  - 이후 high가 TP 이상이면 목표가 도달
  - low가 SL 이하이면 손절 도달
- short:
  - low <= entry <= high 이면 진입 체결
  - 이후 low가 TP 이하이면 목표가 도달
  - high가 SL 이상이면 손절 도달

### 동일 캔들에서 TP와 SL이 모두 닿은 경우

1분봉 이하 데이터가 없으면 순서를 알 수 없으므로 `ambiguous`로 표시한다.

정책 옵션:

- 보수적 검증: SL 우선
- 낙관적 검증: TP 우선
- 중립 검증: ambiguous 제외

대시보드에서는 세 가지 기준의 결과를 모두 보여주는 것을 권장한다.

### 검증 기간

기본값:

- 스캘핑 신호: 6시간
- 데이트레이딩 신호: 당일 장 마감 또는 24시간
- 기간 미지정 신호: 24시간 후 만료

## 시장 데이터

### 1차 구현 후보

- yfinance futures ticker
  - `NQ=F`, `ES=F`, `YM=F`, `GC=F`, `CL=F`
- 장점: 빠른 구현
- 단점: 실시간성/분봉 정확도 한계

### 2차 구현 후보

- broker API
- CME 데이터 벤더
- Polygon, Twelve Data, Interactive Brokers 등

초기에는 yfinance 또는 CSV 업로드 기반으로 검증 엔진을 먼저 완성하고, 데이터 공급자는 나중에 교체 가능하게 인터페이스를 분리한다.

## API 설계

### 화면 진입

```text
GET /ai-dashboard/futures-signals
```

HTML 반환.

### 수집 상태

```text
GET /api/futures-signals/collector/status
POST /api/futures-signals/collector/run
```

### 신호 목록

```text
GET /api/futures-signals?provider=&symbol=&status=&from=&to=
GET /api/futures-signals/{signal_id}
```

### 파싱 재시도

```text
POST /api/futures-signals/messages/{message_id}/parse
POST /api/futures-signals/messages/{message_id}/ignore
```

### 성과검증

```text
POST /api/futures-signals/verify
POST /api/futures-signals/{signal_id}/verify
GET /api/futures-signals/performance/summary
GET /api/futures-signals/performance/by-provider
GET /api/futures-signals/performance/by-symbol
```

## 대시보드 화면 구성

### `/ai-dashboard` 오른쪽 버튼

- 버튼 클릭 시 해외선물 검증 화면으로 이동
- 최근 24시간 신호 수, 미검증 신호 수, 승률 요약을 작은 배지로 표시

예시:

```text
[해외선물 신호검증]
오늘 신호 14건 / 검증 대기 3건 / 7일 승률 58.2%
```

### 해외선물 신호검증 화면

주요 영역:

- 상단 요약
  - 오늘 수집 신호 수
  - 파싱 성공률
  - 검증 완료 수
  - 승률
  - 평균 손익
  - 최대 낙폭
- 신호 테이블
  - 시간, 제공자, 종목, 방향, 진입가, SL, TP, 상태, 결과
- 성과 차트
  - 누적 손익
  - 승률 추이
  - symbol별 손익
- 원문/파싱 비교 패널
  - 텔레그램 원문
  - 파싱된 신호
  - 수동 수정 버튼
- 검증 설정 패널
  - 검증 기간
  - TP/SL 동일 캔들 처리 방식
  - 수수료/슬리피지
  - 계약 수/승수

## 파일 추가 계획

### Backend

```text
src/futures_signals/
  __init__.py
  models.py
  repository.py
  telegram_collector.py
  parser.py
  market_data.py
  verifier.py
  service.py

src/dashboard.py
  - /ai-dashboard/futures-signals route 추가
  - /api/futures-signals/* endpoints 추가
```

추후 `dashboard.py`가 커지는 것을 막기 위해 가능하면 FastAPI router 분리를 고려한다.

```text
src/routes/futures_signals.py
```

### Frontend

```text
web/templates/futures_signals.html
web/static/js/futures_signals.js
web/static/css/futures_signals.css
```

기존 `ai_dashboard.html`에는 오른쪽 버튼만 추가한다.

## 구현 단계

### 1단계: 문서/스키마/샘플 데이터

- DB 스키마 정의
- 샘플 텔레그램 메시지 20개 작성
- 파싱 기대 결과 fixture 작성
- 해외선물 symbol alias 표 작성

완료 기준:

- 샘플 메시지를 파싱해 `futures_signals` 형태로 변환할 수 있다.

### 2단계: 파서 구현

- 정규식 기반 1차 파서
- 종목 alias 정규화
- 방향/진입/SL/TP 추출
- confidence 계산
- 실패 메시지 저장

완료 기준:

- 샘플 메시지 기준 주요 포맷 파싱 성공률 80% 이상

### 3단계: 검증 엔진 구현

- 캔들 데이터 인터페이스 작성
- yfinance 또는 CSV 기반 OHLCV 로딩
- long/short TP/SL 판정
- ambiguous 처리
- 수수료/슬리피지 반영

완료 기준:

- 단일 신호와 다중 신호 검증 테스트 통과

### 4단계: API 구현

- 신호 목록 API
- 수집 상태 API
- 검증 실행 API
- 성과 요약 API

완료 기준:

- 프론트 없이 API만으로 수집/파싱/검증 결과 확인 가능

### 5단계: 대시보드 UI 구현

- `/ai-dashboard` 오른쪽 버튼 추가
- `/ai-dashboard/futures-signals` 화면 추가
- 요약 카드, 테이블, 차트, 원문 비교 패널 구현

완료 기준:

- 브라우저에서 신호 목록과 성과 요약 확인 가능

### 6단계: 텔레그램 실제 연동

- Telethon 세션 설정
- 채널별 수집
- 중복 방지
- 수집 로그
- 수동 실행 버튼

완료 기준:

- 지정 채널의 최근 메시지를 중복 없이 저장

### 7단계: 운영 안정화

- 파싱 실패 목록 관리
- 제공자별 성과 필터
- 수동 수정 UI
- 검증 재실행
- 백업/마이그레이션 스크립트

완료 기준:

- 실사용 채널 기준 1주일 이상 데이터 누적 및 성과검증 가능

## 테스트 계획

### Unit tests

- symbol alias 정규화
- 방향 정규화
- 가격 추출
- TP/SL 추출
- confidence 계산
- long 검증
- short 검증
- 동일 캔들 TP/SL ambiguous 처리

### Integration tests

- 메시지 저장 -> 파싱 -> 신호 저장
- 신호 저장 -> 시장 데이터 로딩 -> 결과 저장
- API summary 응답 검증

### UI smoke test

- `/ai-dashboard` 버튼 표시
- 버튼 클릭 후 검증 화면 이동
- 신호 테이블 렌더링
- 성과 차트 렌더링
- 파싱 실패 메시지 표시

## 리스크와 대응

### 텔레그램 메시지 포맷이 일정하지 않음

대응:

- 원문 저장을 필수로 한다.
- confidence 낮은 신호는 수동 검수 대상으로 분리한다.
- regex 파서 이후 LLM 보조 파서를 선택 기능으로 추가할 수 있게 한다.

### 시장 데이터 정확도 부족

대응:

- 데이터 공급자를 인터페이스로 분리한다.
- 초기에는 yfinance/CSV로 검증 엔진을 완성한다.
- 실사용 전에는 더 신뢰도 높은 분봉 데이터 공급자로 교체한다.

### 자동매매와 혼동 위험

대응:

- 메뉴와 테이블에 `성과검증 전용` 표시를 명확히 둔다.
- 기존 `OrderRouter`, `Approval`, `KIS` 주문 흐름과 연결하지 않는다.
- 실주문 버튼은 만들지 않는다.

### 동일 캔들 내 TP/SL 순서 문제

대응:

- `ambiguous` 상태를 별도로 둔다.
- 보수적/낙관적/중립 기준을 모두 계산해 표시한다.

## 우선순위

1. `/ai-dashboard` 오른쪽에 진입 버튼 추가
2. `futures_signals` 화면 뼈대 추가
3. 샘플 메시지 기반 파서 구현
4. CSV/yfinance 기반 검증 엔진 구현
5. 성과 요약 API와 화면 연결
6. Telethon 실제 수집 연동
7. 수동 검수/재검증 기능 추가

## 최종 목표 화면

```text
/ai-dashboard
  오른쪽 버튼: 해외선물 신호검증

/ai-dashboard/futures-signals
  상단: 수집/파싱/검증 요약
  좌측: 신호 목록
  중앙: 누적 성과 차트
  우측: 텔레그램 원문 + 파싱 결과 + 수동 수정
  하단: 제공자별/종목별 성과 테이블
```

이 구조로 가면 기존 국내주식 자동매매 시스템은 건드리지 않으면서, 텔레그램 기반 해외선물 신호검증 기능을 독립적으로 추가할 수 있다.
