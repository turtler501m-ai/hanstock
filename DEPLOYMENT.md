# 개발 및 VM 배포 흐름

이 프로젝트는 이제 루트 디렉터리 하나만 사용합니다.

- 로컬 개발: `C:\0.DOC\workspace`
- VM 실행: 같은 Git 저장소를 `git pull` 해서 실행
- 각 PC/VM의 `.env`, `.runtime`, `logs`, DB, 토큰 파일은 서로 복사하지 않음

## 로컬에서 개발

처음 한 번만 환경을 준비합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

개발 중 대시보드 실행:

```powershell
.\server.cmd restart
```

브라우저:

```text
http://127.0.0.1:8000
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
./server.sh restart
./server.sh status
```

로그 확인:

```bash
./server.sh logs
./server.sh tail
```

## 안전 설정

실거래를 의도적으로 켜기 전까지는 아래 값을 유지합니다.

```text
DRY_RUN=true
TRADING_ENV=demo
ENABLE_LIVE_TRADING=false
```

## 정리된 구조

이전의 `hanstock_loc/`, `hanstock_vm/` 중복 폴더는 제거했습니다. 앞으로는 루트 프로젝트만 수정하고 커밋하면 됩니다.
