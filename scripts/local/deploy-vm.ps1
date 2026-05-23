param(
    [string]$HostName = $env:HANSTOCK_VM_HOST,
    [string]$User = $(if ($env:HANSTOCK_VM_USER) { $env:HANSTOCK_VM_USER } else { "turtler800" }),
    [string]$RepoPath = $(if ($env:HANSTOCK_VM_PATH) { $env:HANSTOCK_VM_PATH } else { "~/hanstock" }),
    [string]$Branch = "main",
    [string]$Instance = $(if ($env:HANSTOCK_GCP_INSTANCE) { $env:HANSTOCK_GCP_INSTANCE } else { "hanstock-server5" }),
    [string]$Zone = $(if ($env:HANSTOCK_GCP_ZONE) { $env:HANSTOCK_GCP_ZONE } else { "us-central1-b" }),
    [string]$Project = $(if ($env:HANSTOCK_GCP_PROJECT) { $env:HANSTOCK_GCP_PROJECT } else { "hanstock-server" }),
    [string]$KeyPath = $(if ($env:HANSTOCK_SSH_KEY) { $env:HANSTOCK_SSH_KEY } else { (Join-Path $env:USERPROFILE ".ssh\google_compute_engine") }),
    [string]$BackupRoot = $(if ($env:HANSTOCK_VM_BACKUP_ROOT) { $env:HANSTOCK_VM_BACKUP_ROOT } else { "~/hanstock_backups" }),
    [switch]$FreshClone,
    [switch]$SkipPush
)

$ErrorActionPreference = "Stop"

function Get-GcloudPath {
    $default = Join-Path $env:LOCALAPPDATA "Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
    if (Test-Path -LiteralPath $default) {
        return $default
    }

    $command = Get-Command gcloud -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    throw "gcloud command was not found. Set HANSTOCK_VM_HOST manually or install Google Cloud SDK."
}

function Get-SshPath {
    $default = Join-Path $env:WINDIR "System32\OpenSSH\ssh.exe"
    if (Test-Path -LiteralPath $default) {
        return $default
    }

    $command = Get-Command ssh -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    throw "OpenSSH client was not found."
}

function Resolve-GcpHost {
    param(
        [string]$InstanceName,
        [string]$InstanceZone,
        [string]$ProjectId
    )

    $gcloud = Get-GcloudPath
    $ip = & $gcloud compute instances describe $InstanceName `
        --zone $InstanceZone `
        --project $ProjectId `
        --format "value(networkInterfaces[0].accessConfigs[0].natIP)"

    if (-not $ip) {
        throw "Could not find an external IP for $InstanceName."
    }

    return $ip.Trim()
}

$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

if (-not $HostName) {
    $HostName = Resolve-GcpHost -InstanceName $Instance -InstanceZone $Zone -ProjectId $Project
}

$ssh = Get-SshPath
$target = if ($User) { "$User@$HostName" } else { $HostName }

if (-not $SkipPush) {
    $status = git status --porcelain
    if ($status) {
        throw "Working tree is not clean. Commit or stash changes before deploy, or use -SkipPush to deploy the current remote state."
    }

    git push origin $Branch
}

$repoUrl = "https://github.com/turtler501m-ai/hanstock.git"
$remoteCommand = @'
set -e
BRANCH="__BRANCH__"
REPO_PATH="__REPO_PATH__"
REPO_URL="__REPO_URL__"
BACKUP_ROOT="__BACKUP_ROOT__"
FRESH_CLONE="__FRESH_CLONE__"

REPO_PATH="${REPO_PATH/#\~/$HOME}"
BACKUP_ROOT="${BACKUP_ROOT/#\~/$HOME}"

if [ "$FRESH_CLONE" = "1" ] && [ -e "$REPO_PATH" ]; then
  stamp="$(date +%Y%m%d-%H%M%S)"
  backup_path="$BACKUP_ROOT/hanstock-$stamp"
  mkdir -p "$BACKUP_ROOT"
  echo "[deploy] moving existing repo to $backup_path"
  mv "$REPO_PATH" "$backup_path"
fi

if [ ! -d "$REPO_PATH/.git" ]; then
  mkdir -p "$(dirname "$REPO_PATH")"
  git clone "$REPO_URL" "$REPO_PATH"
  if [ -n "${backup_path:-}" ] && [ -f "$backup_path/.env" ] && [ ! -f "$REPO_PATH/.env" ]; then
    echo "[deploy] copying .env from backup"
    cp "$backup_path/.env" "$REPO_PATH/.env"
  fi
fi
cd "$REPO_PATH"
./scripts/vm/update.sh "$BRANCH"
'@

$remoteCommand = $remoteCommand.
    Replace("__BRANCH__", $Branch).
    Replace("__REPO_PATH__", $RepoPath).
    Replace("__REPO_URL__", $repoUrl).
    Replace("__BACKUP_ROOT__", $BackupRoot).
    Replace("__FRESH_CLONE__", $(if ($FreshClone) { "1" } else { "0" }))

Write-Host "[deploy] target: $target"
Write-Host "[deploy] repo: $RepoPath"
Write-Host "[deploy] branch: $Branch"
if ($FreshClone) {
    Write-Host "[deploy] fresh clone: enabled"
    Write-Host "[deploy] backup root: $BackupRoot"
}
if (Test-Path -LiteralPath $KeyPath) {
    $remoteCommand | & $ssh -i $KeyPath -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 $target "bash -s"
} else {
    $remoteCommand | & $ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 $target "bash -s"
}

if ($LASTEXITCODE -ne 0) {
    throw "VM deploy failed with exit code $LASTEXITCODE"
}
