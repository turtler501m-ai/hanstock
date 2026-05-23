# VM/Linux Scripts

VM 또는 Linux 서버에서 사용하는 실행 스크립트입니다.

```bash
./scripts/vm/server.sh restart
./scripts/vm/server.sh status
./scripts/vm/server.sh logs
./scripts/vm/server.sh tail
```

시그널 수집:

```bash
./scripts/vm/poll.sh
./scripts/vm/polld.sh
./scripts/vm/signals.sh
```

GitHub 최신 버전 반영, 의존성 설치, 서버 재시작:

```bash
./scripts/vm/update.sh main
```

로컬 Windows에서는 이 폴더의 스크립트를 사용하지 않습니다.
