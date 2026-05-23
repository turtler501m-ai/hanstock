# Project Analysis

## 프로젝트 목적

`hanstock`은 KIS Open API 기반 국내주식 자동매매와 해외선물 시그널 대시보드를 함께 제공하는 Python/FastAPI 프로젝트입니다. 로컬에서 개발하고 검증한 뒤 GitHub 저장소 `turtler501m-ai/hanstock`에 푸시하고, VM은 같은 저장소를 pull 받아 실행하는 구조로 정리되었습니다.

## 주요 기능

- FastAPI 대시보드: 계좌, 보유종목, 매매 후보, 실행 계획, 승인 대기열, 성과, 리스크 상태 표시
- 국내주식 Seven Split 전략: RSI, SMA, Bollinger Band, MACD, 포트폴리오 비중, 현금 버퍼 기반 주문 계획 생성
- KIS 국내주식 API 연동: 토큰, 잔고, 시세, 일봉, 주문
- KIS 해외선물 API 연동: 해외선물 잔고, 포지션, 주문, 취소, 시세 조회
- Telegram 해외선물 시그널 수집: Telethon 기반 메시지 수집, Claude API 기반 추출, 정규식 fallback
- 해외선물 시그널 검증/실행: 진입가, 손절, 익절, 계약수 파싱, 모의/실거래 실행 상태 관리
- QuantConnect MNQ 연동: 프로젝트 상태, 컴파일, 배포, 주문 API 래핑
- SQLite 기반 런타임 저장소: 거래, 승인, 결정 로그, 시그널 DB
- Slack 알림: 주문 및 오류 알림

## 현재 저장소 기준

- 기준 원격 저장소: `https://github.com/turtler501m-ai/hanstock.git`
- 기준 브랜치: `main`
- 개발 위치: `C:\0.DOC\workspace`
- VM 반영 방식: `git pull origin main` 후 `./scripts/vm/server.sh restart`

## 강점

- 테스트가 넓게 깔려 있습니다. 현재 `python -m unittest discover -s tests` 기준 166개 테스트가 통과합니다.
- 주문 제출에 다중 안전장치가 있습니다. `DRY_RUN`, `TRADING_ENV`, `ENABLE_LIVE_TRADING`, `REQUIRE_APPROVAL`이 함께 작동합니다.
- 대시보드가 운영에 필요한 주요 상태를 한 화면에서 다룹니다.
- 로컬 Windows 실행 스크립트와 VM/Linux 실행 스크립트가 모두 준비되어 있습니다.

## 확인된 리스크

- GitHub Actions 등 일부 기존 운영 파일에 인코딩 깨짐이 남아 있습니다.
- `src/dashboard.py`가 3000줄 이상으로 커져 라우트, 서비스, 환경설정, QuantConnect, 시그널 기능이 한 파일에 섞여 있습니다.
- `.github/workflows/auto_trade.yml`은 일부 한글이 깨져 있고, `database` 브랜치 push 방식도 현재 운영 정책과 재검토가 필요합니다.
- `src/futures_signals/poll.py`에는 기본 Telegram API ID/HASH fallback 값이 코드에 있습니다. 실제 값이면 즉시 제거해야 합니다.
- VM 운영은 새 `scripts/vm` 경로 기준으로 clone 또는 remote 변경 작업이 필요할 수 있습니다.
