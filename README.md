# Hanstock

KIS Open API 기반 국내주식 자동매매와 해외선물 시그널 대시보드를 함께 운영하는 Python/FastAPI 프로젝트입니다.

## 실행 스크립트 구분

로컬 Windows와 VM/Linux 실행 파일을 분리했습니다.

```text
scripts/local/   로컬 Windows 개발 PC용
scripts/vm/      VM 또는 Linux 서버용
```

## 로컬 개발

```powershell
cd C:\0.DOC\workspace
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

대시보드 실행:

```powershell
.\scripts\local\server.cmd restart
```

상태와 로그:

```powershell
.\scripts\local\server.cmd status
.\scripts\local\server.cmd logs
.\scripts\local\server.cmd tail
```

접속:

```text
http://127.0.0.1:8000
```

검증:

```powershell
powershell -ExecutionPolicy Bypass -File tools\verify-local.ps1
python -m unittest discover -s tests
```

## VM 실행

VM에서는 코드를 직접 수정하지 않고 GitHub에서 pull 받아 실행합니다.

최초 준비:

```bash
git clone https://github.com/turtler501m-ai/hanstock.git
cd hanstock
cp .env.example .env
python3 -m pip install -r requirements.txt
```

업데이트 및 재시작:

```bash
git pull origin main
python3 -m pip install -r requirements.txt
./scripts/vm/server.sh restart
./scripts/vm/server.sh status
```

로그:

```bash
./scripts/vm/server.sh logs
./scripts/vm/server.sh tail
```

## 자동 배포

로컬에서 VM으로 pull/restart까지 자동 실행:

```powershell
.\scripts\local\deploy-vm.ps1
```

기본 VM 대상은 `hanstock-server5`입니다. SSH 접속만 열려면:

```powershell
.\scripts\local\connect-vm.ps1
```

VM 내부에서 직접 최신 버전을 반영할 때:

```bash
./scripts/vm/update.sh main
```

VM 폴더를 새로 받아 현행화하려면 기존 폴더를 백업하고 다시 clone합니다. 기존 폴더에 `.env`가 있으면 새 폴더로 복사됩니다.

```powershell
.\scripts\local\deploy-vm.ps1 -FreshClone
```

## 주요 진입점

- 대시보드: `src.dashboard:app`
- 자동매매 엔진: `python src\trader.py`
- 해외선물 시그널 poller: `python -m src.futures_signals.poll`
- 로컬 서버 스크립트: `scripts/local/server.cmd`
- VM 서버 스크립트: `scripts/vm/server.sh`

## 안전 기본값

실거래를 의도적으로 켜기 전까지는 아래 값을 유지합니다.

```text
DRY_RUN=true
TRADING_ENV=demo
ENABLE_LIVE_TRADING=false
REQUIRE_APPROVAL=true
```

## 문서

프로젝트 분석과 운영 문서는 `doc/S1.한스톡사용설명서.md`에 있습니다.
