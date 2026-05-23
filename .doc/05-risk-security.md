# Risk and Security

## 실거래 안전장치

실제 주문 제출은 아래 조건을 모두 확인해야 합니다.

```text
DRY_RUN=false
TRADING_ENV=real
ENABLE_LIVE_TRADING=true
```

`REQUIRE_APPROVAL=true`이면 주문은 즉시 제출되지 않고 승인 대기열에 들어갑니다. 대시보드에서 승인해야 주문 처리 단계로 넘어갑니다.

## 기본 권장값

```text
DRY_RUN=true
TRADING_ENV=demo
ENABLE_LIVE_TRADING=false
REQUIRE_APPROVAL=true
```

## Git에 올리면 안 되는 파일

- `.env`
- `.runtime/`
- `logs/`
- `data/*.db`
- `data/*.sqlite`
- `data/kis_token.json`
- Telegram session 파일
- API key, token, account number가 들어간 임시 파일

## 현재 보안상 점검할 항목

1. `src/futures_signals/poll.py`의 `TELEGRAM_API_ID`, `TELEGRAM_API_HASH` 기본값을 제거해야 합니다.
2. GitHub Actions의 자동매매 workflow는 인코딩과 운영 정책을 재검토해야 합니다.
3. VM `.env`는 로컬 `.env`와 별도로 관리해야 합니다.
4. 실거래 전에는 작은 수량, demo 환경, 승인 모드로 충분히 검증해야 합니다.
5. KIS API rate limit 오류가 반복되면 캐시와 호출 간격을 먼저 확인해야 합니다.

## 장애 대응 순서

1. `./server.sh status` 또는 `.\server.cmd status`로 서버 상태 확인
2. `logs` 또는 `.runtime`의 stderr 로그 확인
3. `.env` 설정 확인
4. `python -m unittest discover -s tests` 실행
5. 최근 커밋 diff 확인
6. 실거래 스위치가 켜져 있다면 즉시 `DRY_RUN=true`로 전환
