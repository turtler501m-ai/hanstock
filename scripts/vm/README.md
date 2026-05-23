# VM/Linux Scripts

VM 또는 Linux 서버에서 사용하는 스크립트입니다. Windows 로컬에서는 이 폴더의 스크립트를 직접 실행하지 않습니다.

## 대시보드 서버

```bash
./scripts/vm/server.sh restart
./scripts/vm/server.sh status
./scripts/vm/server.sh logs
./scripts/vm/server.sh tail
```

## 최신 코드 반영

```bash
./scripts/vm/update.sh main
```

`update.sh`는 아래 순서로 동작합니다.

1. `.env` 존재 여부 확인
2. `git fetch`
3. 지정 브랜치 checkout/pull
4. `.venv` 없으면 생성
5. `requirements.txt` 설치
6. 대시보드 재시작
7. 서버 상태 출력

## Telegram 시그널 수집

```bash
./scripts/vm/poll.sh
./scripts/vm/polld.sh
./scripts/vm/signals.sh
```

강제 1회 실행이 필요하면:

```bash
POLLING_FORCE_RUN=1 ./scripts/vm/poll.sh
```
