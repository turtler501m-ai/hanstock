$ErrorActionPreference = "Stop"

& "$PSScriptRoot\connect-vm.ps1" `
    -User "turtler800" `
    -Instance "hanstock-server5" `
    -Zone "us-central1-b" `
    -Project "hanstock-server" `
    @args
