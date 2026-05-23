# Architecture

## 디렉터리 구조

```text
src/
  api/                 KIS, KIS 해외선물, QuantConnect API 클라이언트
  db/                  공통 DB repository
  futures_signals/     해외선물 시그널 수집, 파싱, 저장, 검증, 실행
  notifier/            Slack 알림
  strategy/            Seven Split 전략, 지표, 리스크, 라우팅
  utils/               로깅 유틸
  dashboard.py         FastAPI 대시보드 엔트리포인트
  trader.py            자동매매 엔진 엔트리포인트
  config.py            환경변수 설정

web/
  templates/           Jinja/HTML 화면
  static/              CSS, JavaScript

tests/                 unittest 기반 테스트
tools/                 로컬 검증, 서버, 계좌 점검 도구
quantconnect/          MNQ paper auto 알고리즘
```

## 실행 엔트리포인트

- 대시보드: `src.dashboard:app`
- 트레이더 직접 실행: `python src\trader.py`
- 스케줄러: `src/scheduler.py`
- 해외선물 Telegram poller: `src/futures_signals/poll.py`
- 로컬 서버 스크립트: `scripts/local/server.cmd`, `tools/server.ps1`
- VM 서버 스크립트: `scripts/vm/server.sh`

## 대시보드 흐름

1. `scripts/local/server.cmd` 또는 `scripts/vm/server.sh`가 `uvicorn src.dashboard:app`을 실행합니다.
2. `src/dashboard.py`가 `.env`를 로드하고 FastAPI 앱을 구성합니다.
3. 정적 파일은 `web/static`, 화면은 `web/templates`에서 제공합니다.
4. API 라우트는 KIS, SQLite, 캐시 파일, QuantConnect, Telegram collector 상태를 읽어 화면에 전달합니다.

## 국내주식 자동매매 흐름

1. `src/trader.py`가 설정과 KIS 클라이언트를 초기화합니다.
2. 계좌 잔고와 보유종목을 조회합니다.
3. `src/strategy/seven_split.py`가 보유종목 신호, 매수 후보, 포트폴리오 계획을 계산합니다.
4. 주문은 `DRY_RUN`, `TRADING_ENV`, `ENABLE_LIVE_TRADING`, `REQUIRE_APPROVAL` 조건을 통과해야 합니다.
5. 승인 필요 시 SQLite 승인 대기열에 저장하고, 승인 후 주문을 제출합니다.
6. 거래 결과와 결정 로그는 런타임 DB에 저장합니다.

## 해외선물 시그널 흐름

1. Telegram collector 또는 poller가 채널 메시지를 수집합니다.
2. Claude API 또는 fallback parser가 메시지에서 시그널을 추출합니다.
3. `src/futures_signals/parser.py`가 종목, 방향, 진입가, 손절, 익절, 계약수를 정규화합니다.
4. 시그널은 `.runtime/signals.db`에 저장됩니다.
5. 대시보드에서 검증, 모의 성과, paper/live 실행 상태를 조회합니다.
6. 실행은 `src/futures_signals/executor.py`가 상태 파일과 KIS 해외선물 API를 사용합니다.

## 저장소와 런타임 파일

- Git 추적 대상: `src`, `web`, `tests`, `tools`, 설정 예시, 운영 스크립트
- Git 제외 대상: `.env`, `.runtime`, `logs`, DB, token/session/cache 파일
- 주요 런타임 파일:
  - `.runtime/trades.sqlite`
  - `.runtime/signals.db`
  - `.runtime/balance_snapshot.json`
  - `.runtime/executor_state.json`
  - `.runtime/futures_telegram*`
