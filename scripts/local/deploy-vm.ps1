param(
    [string]$HostName = $env:HANSTOCK_VM_HOST,
    [string]$User = $env:HANSTOCK_VM_USER,
    [string]$RepoPath = $(if ($env:HANSTOCK_VM_PATH) { $env:HANSTOCK_VM_PATH } else { "~/hanstock" }),
    [string]$Branch = "main",
    [switch]$SkipPush
)

$ErrorActionPreference = "Stop"

if (-not $HostName) {
    throw "Set -HostName or HANSTOCK_VM_HOST. Example: .\scripts\local\deploy-vm.ps1 -HostName 1.2.3.4 -User ubuntu"
}

$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

$target = if ($User) { "$User@$HostName" } else { $HostName }

if (-not $SkipPush) {
    $status = git status --porcelain
    if ($status) {
        throw "Working tree is not clean. Commit or stash changes before deploy, or use -SkipPush to deploy the current remote state."
    }

    git push origin $Branch
}

$remoteCommand = "cd $RepoPath && ./scripts/vm/update.sh $Branch"

Write-Host "[deploy] target: $target"
Write-Host "[deploy] repo: $RepoPath"
Write-Host "[deploy] branch: $Branch"
ssh $target $remoteCommand
