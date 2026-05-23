# Local Windows Scripts

로컬 개발 PC에서 사용하는 Windows 실행 스크립트입니다.

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

VM 자동 배포:

```powershell
.\scripts\local\deploy-vm.ps1
```

기본값은 기존 `hanstock-server5.ps1` 접속 정보와 같습니다.

```text
GCP instance: hanstock-server5
zone: us-central1-b
project: hanstock-server
user: turtler800
key: ~/.ssh/google_compute_engine
repo: ~/hanstock
```

VM SSH 접속:

```powershell
.\scripts\local\connect-vm.ps1
```

VM 폴더를 백업하고 새로 clone:

```powershell
.\scripts\local\deploy-vm.ps1 -FreshClone
```

VM에서는 이 폴더의 스크립트를 사용하지 않습니다.
