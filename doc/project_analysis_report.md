# 🧭 Hanstock(한스톡) 프로젝트 종합 분석 보고서

이 보고서는 국내주식 자동매매, AI 전략 검증 생명주기, 해외선물 시그널 파싱/실행, 그리고 QuantConnect 연동 기능이 유기적으로 통합된 **Hanstock 프로젝트**의 아키텍처, 기술 스택, 핵심 모듈 및 데이터베이스 구조, 그리고 운영 통제 장치들을 상세 분석한 보고서입니다.

---

## 🛠️ 1. 기술 스택 (Technology Stack)

Hanstock은 현대적인 백엔드 아키텍처와 경량 데이터베이스, LLM 및 강화학습(RL) 모델 연동, 그리고 풍부한 프론트엔드 비주얼을 함께 담아낸 올인원 트레이딩 대시보드 애플리케이션입니다.

* **Backend Core**: Python 3.10+ & FastAPI (Uvicorn)
* **Trading Interface (API)**: 한국투자증권(KIS) 국내주식 Open API, KIS 해외선물 Open API, QuantConnect API
* **Database & Persistence**: SQLite3 (로컬 개발용) & PostgreSQL (실무 배포용, `psycopg2`) 호환 계층 설계
* **AI & Machine Learning**: 
  - **LLM**: OpenAI GPT-5-mini (Structured Outputs 기반 매수 타당성/확신도 판별)
  - **ML**: LightGBM (순위 예측 모델 학습 및 서빙)
  - **RL**: Stable-Baselines3 & Gymnasium (PPO 강화학습 기반 최적 포트폴리오 비중 유도)
* **Frontend**: HTML5 (Semantic Markup), Vanilla CSS & Tailwind, Vanilla JS (Rich dynamic SPA 패턴, uplot.js/charts.js 등을 사용한 반응형 그래프 시각화)
* **Scraper & Parsing**: Telethon (Telegram API 메시지 실시간 수집), Claude API 및 정규식 Fallback
* **Safety/Notification**: Slack Webhooks (`incoming-webhook`), KIS API Throttling & Circuit Breaker

---

## 📂 2. 프로젝트 폴더 구조 및 규칙

`AGENTS.md` 및 `S1.한스톡사용설명서.md`에 정의된 한스톡의 디렉터리 배치 규칙은 매우 엄격하며 체계적으로 구분되어 있습니다.

```text
C:\MSF-LOC\workstudy\hanstock\
├── .runtime/               # 런타임 산출물 (SQLite DB, KIS 토큰, 캐시 파일, 로그)
├── config/                 # checked-in 비밀이 아닌 설정 파일 (예: Telegram 채널 목록)
├── data/                   # KIS 토큰 캐시 및 로컬 데이터
├── doc/                    # 통합 설명서 및 설계/진행현황 마크다운 문서들
├── logs/                   # 애플리케이션 실행 로그 디렉터리
├── scripts/
│   ├── local/              # Windows 로컬 개발 전용 실행 스크립트 (.cmd, .ps1)
│   └── vm/                 # GCP VM/Linux 전용 배포 및 무중단 운영 스크립트 (.sh)
├── src/                    # 파이썬 애플리케이션 소스 코드
│   ├── api/                # KIS, KIS 해외선물, QuantConnect, Bybit 외부 API 클라이언트
│   ├── dashboard/          # FastAPI 앱 코어 및 도메인별 분할 라우트 (routes/)
│   ├── db/                 # SQLite/PostgreSQL 데이터 저장소 접근 계층 (Repository)
│   ├── futures_signals/    # 텔레그램 해외선물 시그널 수집, 파싱, 검증, 실행 모듈
│   ├── strategy/           # Seven Split, Heuristics, AI 랭커 및 배분기, 지표 모듈
│   └── utils/              # 공통 유틸리티 (로깅 등)
├── tests/                  # unittest 기반의 견고한 160개+ 테스트 스위트
├── tools/                  # 로컬 계좌 점검, 임시 마이그레이션, 서버 실행 보조 도구
├── web/
│   ├── static/             # JS (app.js, env_settings.js 등 200KB+) 및 CSS 스타일시트
│   └── templates/          # Jinja2 템플릿 파일 (index.html, fragments/)
└── requirements.txt        # 패키지 의존성 파일 (RL 모델용 stable-baselines3 포함)
```

---

## ⚙️ 3. 핵심 기능 모듈 상세 분석

### 📈 3.1 국내주식 Seven Split 자동매매 엔진 (`src/trader.py` & `src/strategy/`)
* **세븐 스플릿(Seven Split) 전략**: RSI, MACD, Bollinger Band, SMA 기술적 지표 및 사용자가 구성한 매매 룰 조합을 바탕으로 보유 종목의 추가 매수(`buy`), 이익 실현(`sell`), 혹은 관망(`hold`) 판단을 수행합니다.
* **스캔 및 후보군 탐색**: 관심종목(Watchlist)과 거래량 상위 종목에서 매수 후보를 추려낸 뒤, **룰 기반 점수**와 **AI 가중 점수**를 평균내어 랭킹을 매깁니다.
* **안전 결합 모델**: OpenAI GPT-5-mini 모델에 종목별 Feature 및 사용자의 '전략 프로필 설명'을 주입하여 매수 적합성과 모델 확신도(Confidence)를 평가받아 Heuristics에 융합합니다. API 장애나 속도 초과 시 Heuristic 룰 점수로 즉각 Fallback하여 중단을 예방합니다.

### 🤖 3.2 AI 전략 관리 및 검증 생명주기 (`src/db/` & `src/dashboard/routes/stock.py`)
사용자가 새로운 AI 전략을 등록한 뒤 실전에 배치하기까지의 안전 게이트와 상태 관리가 고도화되어 있습니다.

* **전략 프로필 JSON화**: `strategy_type`, `risk_level`, `focus/avoid indicators`, `min_rule_score_for_ai`, `allow_candidate_promotion` 등의 위험 매개변수를 Profile로 관리합니다.
* **체계적 상태 관리 (State Machine)**:
  1. `draft`: 신규 생성된 전략
  2. `verified`: 정적 정합성 및 OpenAI API 접속 검증 완료
  3. `backtested`: 과거 데이터 백테스트 리포트 산출 및 승인 기준 통과
  4. `paper_running`: 모의투자 상태로 일정 일수 동안 테스트 후보 생성
  5. `paper_passed`: 모의 검증 완료
  6. `approved`: 실전 투입 승인 (Active 전략 임명 가능)
  7. `retired`: 비활성화 또는 성능 저하로 퇴출됨
* **승인 방어막**: `POST /api/ai-strategies/{id}/approve` API는 정적 검증 여부, 백테스트 완결 여부, 모의운용 일수 충족 여부를 체크하여 미충족 시 **`409 Conflict` 오류를 내고 승인을 철저히 가로막습니다.**

### 📡 3.3 텔레그램 해외선물 시그널 시스템 (`src/futures_signals/`)
텔레그램 해외선물 리딩 방 등에서 텍스트 시그널을 수집하여 검증하고 가상/실제 주문을 내는 독자적인 서브시스템입니다.

* **메시지 콜렉터 (`telegram_collector.py` / `poll.py`)**: Telethon 라이브러리를 사용하여 지정된 채널들로부터 메시지를 실시간 이벤트를 통해 파이싱합니다.
* **LLM 시그널 추출**: Claude 3.5 Sonnet / Haiku 모델의 프롬프트와 정규식 Fallback을 조합하여 `진입가`, `손절가(SL)`, `익절가(TP)`, `계약수`를 정밀 추출하여 `.runtime/signals.db`에 영속화합니다.
* **성과 검증기 (`verifier.py`)**: KIS 해외선물 시세를 스트리밍 혹은 분봉으로 조회하여 해당 시그널이 실제 익절되었는지, 손절되었는지를 분 단위로 역추적하여 성과(Win-rate, PnL)를 백테스팅합니다.
* **자동 실행 엔진 (`executor.py`)**: KIS 해외선물 계좌(모의/실계좌) API와 물리적으로 동기화하여 시그널 도달 시 지정가 혹은 시장가 주문을 실시간 송신합니다.

### 🌐 3.4 QuantConnect MNQ paper auto 연동 (`src/integrations/quantconnect/`)
* **QuantConnect API 래핑**: 클라우드 기반의 알고리즘 트레이딩 플랫폼인 QuantConnect의 REST API를 연동하여 MNQ(Micro Nasdaq 100 E-mini) Paper Trading 상태 모니터링, 프로젝트 재컴파일, 원격 Live 배포 및 선물 주문 연동 명령을 대시보드 단일 화면으로 통합 제어합니다.

---

## 🗄️ 4. 데이터베이스 및 스키마 구조 (SQLite / Postgres)

`src/db/repository.py`를 통해 관리되는 주요 테이블 스키마와 목적은 다음과 같습니다.

### 1) `ai_strategies` (AI 전략 목록 및 메타)
AI 전략의 사양, 설정 매개변수 및 실전 적용 전 검증 스탬프를 저장합니다.
* `id` (TEXT PRIMARY KEY), `name` (TEXT), `provider` (TEXT), `model` (TEXT), `weight` (REAL)
* `status` (TEXT): draft, verified, backtested, paper_running, paper_passed, approved, retired, review_required
* `profile_json` (TEXT): 전략 프로필 위험 설정 (avoid, focus, risk_level 등)
* `strategy_version` (INTEGER), `profile_hash` (TEXT), `last_verified_at` (TEXT), `last_backtested_at` (TEXT) 등

### 2) `scanned_candidates` (매수 후보 이력)
자동매매 사이클 돌 때마다 스캔된 후보 종목들과, 당시 종목을 고른 AI 전략 정보 및 후속 수익률 정보를 기록합니다.
* `symbol` (TEXT), `name` (TEXT), `score` (INTEGER), `reasons` (TEXT), `rule_score` (REAL), `ml_score` (REAL), `final_score` (REAL)
* `strategy_id` (TEXT), `strategy_version` (INTEGER), `profile_hash` (TEXT) -> **투명한 추적성 보장**
* `forward_return_1d`, `forward_return_5d`, `forward_return_20d` (REAL) -> **전략 성과 측정용 후속 수익률**

### 3) `trades` (거래 실행 체결 기록)
실제 또는 모의 주문의 체결 결과와 상세 정보를 저장합니다.
* `symbol`, `action` (buy/sell), `qty`, `price`, `ok` (성공여부), `env` (demo/real), `dry_run` (1/0)
* `strategy_id`, `strategy_version`, `profile_hash` -> **어떤 전략 버전의 판단에 의해 들어간 주문인지 오딧팅 가능**
* `source_approval_id` -> 승인 대기열 연계 외래키

### 4) `approvals` (주문 승인 대기열)
`REQUIRE_APPROVAL=true`일 때, 주문이 전송되기 전 대기하고 사용자의 대시보드 승인을 기다리는 가상 큐입니다.
* `symbol`, `qty`, `price`, `action`, `status` (pending, approved, rejected)
* `strategy_id`, `strategy_version`, `profile_hash`, `source_candidate_id`

---

## 🔒 5. 프로덕션 안전 및 위험 통제 시스템 (Safety Systems)

실제 주식 계좌와 물리적으로 자금이 오가는 서비스이므로 겹겹이 쳐진 안전장치가 돋보입니다.

```text
┌────────────────────────────────────────────────────────┐
│                      Safety Gate                       │
├────────────────────────────────────────────────────────┤
│  1. DRY_RUN=True Check   ──> 주문 로깅만 실행, 통신 차단  │
│  2. TRADING_ENV=demo     ──> 실계좌가 아닌 KIS 모의투자 송신│
│  3. REQUIRE_APPROVAL=1   ──> 대시보드 수동 승인 대기열 적재│
│  4. API Rate Limit       ──> 최소 2초 대기 (_kis_order_throttle)│
│  5. Position Limit       ──> Max Positions(3개) 초과 시 매수 차단 │
│  6. Single Weight        ──> 단일 종목 30% 비중 초과 시 매칭 Sizing │
│  7. Circuit Breaker      ──> KIS 통신장애 3회 연속 시 API Cooldown  │
└────────────────────────────────────────────────────────┘
```

* **KIS API Throttling & Exception Handling**:
  - `KIStockAPI` 내에서 `_kis_order_throttle()` 함수를 사용하여 KIS 서버로 주문이나 조회가 연달아 발생할 때 강제로 2초 이상 슬립(Sleep)을 주어 Connection Disconnect 장애를 예방합니다.
  - KIS 통신 구간을 예외 처리(`try...except`)하여 예외 발생 시 `fallback` 빈 딕셔너리를 안정적으로 리턴하고, 연속 오류 발생 시 즉각 회로(Circuit)를 차단하여 Slack 알림을 송신합니다.
* **Slack Chunking (슬랙 알림 자동 쪼개기)**:
  - 매수 후보군이 너무 많거나 대형 배치 스케줄러 로그가 3,000자를 넘어가면 Slack API에서 수신을 거부(`HTTP 400`)합니다.
  - 이를 예방하기 위해 알림 유틸리티에 **2,800자 자동 슬라이싱(Chunking)** 분할 발송 엔진을 장착해 누락 없는 예외 리포팅을 유지합니다.

---

## 🚀 6. 종합 의견 및 개선 제안 (Recommendations)

현재 Hanstock 프로젝트는 **테스트 자동화 범위가 넓고, 리스크 통제 수단이 촘촘하며, 최신 트렌드인 AI 전략의 검증 라이프사이클을 견고하게 적용한 훌륭한 프로토타입** 단계입니다.
여기서 실거래 운영의 완성도를 극대화하기 위해 다음 개선안을 제시합니다.

1. **`core.py` (120KB) 모듈 분리**
   - 현재 `src/dashboard/core.py`가 모든 서비스 로직을 가지고 있어 비대합니다. 이미 `routes/` 아래로 엔드포인트가 일부 격리되었으므로, 핵심 비즈니스 로직(Candidates, Signals, Optimizer)을 `src/dashboard/services/` 등의 독립 모듈로 정형화하는 것을 권장합니다.
2. **AI 전략 성과 배치 실현**
   - `scanned_candidates` 테이블에 이미 `forward_return_1d`, `5d`, `20d` 컬럼이 설계되어 있습니다. 하루 한 번 yfinance 또는 KIS 일봉을 기반으로 과거 후보들의 N일 후 종가를 매칭해 주는 **배치 스케줄러(`src/scheduler.py`) 태스크를 구체화**하면, 전략별 실질 적중률을 시각화할 수 있습니다.
3. **OpenAI 비용 및 토큰 관리 화면**
   - `token_usage` 테이블에 기록되는 호출 횟수와 토큰 소비 추이를 대시보드의 '환경설정' 혹은 'AI 전략' 탭에 요약 차트로 연동하여 일일 LLM API 비용을 사용자가 직접 제어할 수 있도록 보강합니다.
