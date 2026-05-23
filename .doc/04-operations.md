# Operations

## 대시보드 운영

Windows 로컬:

```powershell
.\server.cmd restart
```

Linux/VM:

```bash
./server.sh restart
```

공통 접속 주소:

```text
http://127.0.0.1:8000
```

VM 외부 접속이 필요하면 방화벽, 프록시, 바인딩 주소를 별도로 검토해야 합니다. 현재 스크립트는 `127.0.0.1` 기준입니다.

## 트레이더 실행

```powershell
python src\trader.py
```

주요 모드:

- `DRY_RUN=true`: 주문 API 제출 차단, 기록/계획 중심
- `TRADING_ENV=demo`: 모의 환경
- `TRADING_ENV=real`: 실계좌 환경
- `ENABLE_LIVE_TRADING=true`: 실거래 최종 허용 스위치
- `REQUIRE_APPROVAL=true`: 주문 승인 대기열 사용

## 해외선물 시그널 수집

필수 환경변수:

```text
TELEGRAM_API_ID=
TELEGRAM_API_HASH=
TELEGRAM_SESSION_NAME=.runtime/futures_telegram
TELEGRAM_TARGET_CHANNELS=
ANTHROPIC_API_KEY=
```

수집/인증은 대시보드 API와 `tools/telegram-login.py`를 통해 관리합니다.

## QuantConnect MNQ

필수 환경변수:

```text
QUANTCONNECT_USER_ID=
QUANTCONNECT_API_TOKEN=
QUANTCONNECT_PROJECT_ID=
QUANTCONNECT_LIVE_NODE_ID=
```

관련 코드:

- `src/api/quantconnect_api.py`
- `quantconnect/mnq_paper_auto/main.py`
- `web/templates/fragments/futures_tab_quantconnect.html`

## 로그와 캐시

- 서버 로그: `.runtime/dashboard-server.log`, `.runtime/dashboard-server.err.log`
- 일반 로그: `logs/`
- 대시보드 캐시: `.runtime/*snapshot.json`
- 거래 DB: `.runtime/trades.sqlite`
- 시그널 DB: `.runtime/signals.db`

문제가 생기면 먼저 서버 로그, `.env`, KIS/Telegram/QuantConnect 인증 상태를 확인합니다.
