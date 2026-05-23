# 개발 및 VM 배포 흐름

이 프로젝트는 로컬 Windows 개발과 VM/Linux 실행을 명확히 분리합니다.

```text
scripts/local/   로컬 Windows 개발 PC용
scripts/vm/      VM 또는 Linux 서버용
```

## 로컬에서 개발

처음 한 번만 환경을 준비합니다.

```powershell
cd C:\0.DOC\workspace
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

개발 중 대시보드 실행:

```powershell
.\scripts\local\server.cmd restart
```

상태와 로그:

```powershell
.\scripts\local\server.cmd status
.\scripts\local\server.cmd logs
.\scripts\local\server.cmd tail
```

수정 후 검증:

```powershell
powershell -ExecutionPolicy Bypass -File tools\verify-local.ps1
python -m unittest discover -s tests
```

검증이 끝나면 커밋하고 푸시합니다.

```powershell
git status
git add .
git commit -m "변경 내용 요약"
git push origin main
```

## VM에 반영

VM에서는 코드를 직접 수정하지 않고, 로컬에서 푸시한 버전을 받아 실행합니다.

```bash
cd /path/to/hanstock
git pull origin main
python3 -m pip install -r requirements.txt
./scripts/vm/server.sh restart
./scripts/vm/server.sh status
```

로그 확인:

```bash
./scripts/vm/server.sh logs
./scripts/vm/server.sh tail
```

시그널 수집:

```bash
./scripts/vm/poll.sh
./scripts/vm/polld.sh
./scripts/vm/signals.sh
```

## 분리 원칙

- 로컬에서는 `scripts/local`만 사용합니다.
- VM에서는 `scripts/vm`만 사용합니다.
- `.env`, `.runtime`, `logs`, DB, 토큰 파일은 PC와 VM 사이에서 복사하지 않습니다.

## 안전 설정

실거래를 의도적으로 켜기 전까지는 아래 값을 유지합니다.

```text
DRY_RUN=true
TRADING_ENV=demo
ENABLE_LIVE_TRADING=false
```
