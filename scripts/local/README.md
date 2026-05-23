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
$env:HANSTOCK_VM_HOST="1.2.3.4"
$env:HANSTOCK_VM_USER="ubuntu"
$env:HANSTOCK_VM_PATH="~/hanstock"
.\scripts\local\deploy-vm.ps1
```

VM에서는 이 폴더의 스크립트를 사용하지 않습니다.
