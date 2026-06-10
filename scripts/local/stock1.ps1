$ErrorActionPreference = "Stop"

# 신규 운영 VM (instance-20260610-stock1 / us-central1-c / project-c48329d1-72a5-4699-8ff).
# gcloud 계정에 해당 프로젝트 compute.instances.get 권한이 없어 gcloud 해석 대신 IP를 직접 지정한다.
# IP가 바뀌면 아래 -HostName 값 또는 $env:HANSTOCK_VM_HOST를 갱신할 것.
& "$PSScriptRoot\connect-vm.ps1" `
    -HostName "34.69.241.175" `
    -User "turtler801" `
    @args
