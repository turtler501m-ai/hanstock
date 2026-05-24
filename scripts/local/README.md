# Local Windows Scripts

로컬 Windows 개발 PC에서 사용하는 스크립트입니다.

## 대시보드 서버

권장 명령은 프로젝트 루트의 래퍼입니다.

```powershell
.\server.cmd restart
.\server.cmd status
.\server.cmd logs
.\server.cmd tail
```

직접 호출하려면 아래 명령을 사용합니다.

```powershell
.\scripts\local\server.cmd restart
```

`scripts/local/server.cmd`는 `tools/server.ps1`을 호출합니다.

## 로컬 검증

```powershell
.\verify.cmd
```

내부적으로 `tools/verify-local.ps1`을 실행합니다.

## Telegram 1회 수집

```powershell
.\scripts\local\telegram_poll.ps1
```

## VM 배포와 접속

```powershell
.\deploy-vm.ps1
.\deploy-vm.ps1 -SkipPush
.\deploy-vm.ps1 -FreshClone
.\connect-vm.ps1
.\check-vm.ps1
.\vm-dashboard.ps1
```

기본 VM 대상:

```text
GCP instance: hanstock-server5
zone: us-central1-b
project: hanstock-server
user: turtler800
key: ~/.ssh/google_compute_engine
repo: ~/hanstock
```

환경변수로 대상을 바꿀 수 있습니다.

```powershell
$env:HANSTOCK_GCP_INSTANCE="hanstock-server5"
$env:HANSTOCK_GCP_ZONE="us-central1-b"
$env:HANSTOCK_GCP_PROJECT="hanstock-server"
$env:HANSTOCK_VM_USER="turtler800"
$env:HANSTOCK_VM_PATH="~/hanstock"
```
