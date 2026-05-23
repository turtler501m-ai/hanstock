# 실행 스크립트 구분

실행 스크립트는 로컬 Windows용과 VM/Linux용을 분리해서 관리합니다.

## 로컬 Windows

위치: `scripts/local/`

```powershell
.\scripts\local\server.cmd restart
.\scripts\local\server.cmd status
.\scripts\local\server.cmd logs
.\scripts\local\server.cmd tail
```

Telegram poll 1회 실행:

```powershell
.\scripts\local\telegram_poll.ps1
```

## VM/Linux

위치: `scripts/vm/`

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

## 원칙

- 로컬에서는 `scripts/local`만 사용합니다.
- VM에서는 `scripts/vm`만 사용합니다.
- 양쪽 모두 프로젝트 루트에서 실행해도 되고, 스크립트가 내부적으로 루트 경로를 찾아갑니다.
