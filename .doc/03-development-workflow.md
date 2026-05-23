# Development Workflow

## 기본 원칙

- 로컬에서만 개발합니다.
- VM에서는 직접 수정하지 않습니다.
- 변경은 GitHub `hanstock` 저장소의 `main` 브랜치로 관리합니다.
- 실거래 관련 변경은 테스트와 설정 확인을 먼저 합니다.

## 로컬 준비

```powershell
cd C:\0.DOC\workspace
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

## 로컬 실행

```powershell
.\server.cmd restart
```

접속:

```text
http://127.0.0.1:8000
```

상태/로그:

```powershell
.\server.cmd status
.\server.cmd logs
.\server.cmd tail
```

## 검증

```powershell
powershell -ExecutionPolicy Bypass -File tools\verify-local.ps1
python -m unittest discover -s tests
```

## 커밋과 푸시

```powershell
git status
git add .
git commit -m "변경 내용 요약"
git push origin main
```

## VM 반영

VM에서 최초 1회:

```bash
git clone https://github.com/turtler501m-ai/hanstock.git
cd hanstock
cp .env.example .env
python3 -m pip install -r requirements.txt
```

이후 업데이트:

```bash
cd /path/to/hanstock
git pull origin main
python3 -m pip install -r requirements.txt
./server.sh restart
./server.sh status
```

로그:

```bash
./server.sh logs
./server.sh tail
```

## 변경 전 체크리스트

- `.env` 또는 토큰 파일을 커밋하지 않았는가
- 실거래 안전값이 의도치 않게 바뀌지 않았는가
- 새 기능에 테스트가 필요한가
- 대시보드 화면 변경이면 브라우저에서 확인했는가
- VM 전용 설정을 코드에 하드코딩하지 않았는가
