param(
    [string]$HostName = $env:HANSTOCK_VM_HOST,
    [string]$User = $(if ($env:HANSTOCK_VM_USER) { $env:HANSTOCK_VM_USER } else { "turtler800" }),
    [string]$RepoPath = $(if ($env:HANSTOCK_VM_PATH) { $env:HANSTOCK_VM_PATH } else { "~/hanstock" }),
    [string]$Instance = $(if ($env:HANSTOCK_GCP_INSTANCE) { $env:HANSTOCK_GCP_INSTANCE } else { "hanstock-server5" }),
    [string]$Zone = $(if ($env:HANSTOCK_GCP_ZONE) { $env:HANSTOCK_GCP_ZONE } else { "us-central1-b" }),
    [string]$Project = $(if ($env:HANSTOCK_GCP_PROJECT) { $env:HANSTOCK_GCP_PROJECT } else { "hanstock-server" }),
    [string]$KeyPath = $(if ($env:HANSTOCK_SSH_KEY) { $env:HANSTOCK_SSH_KEY } else { (Join-Path $env:USERPROFILE ".ssh\google_compute_engine") }),
    [int]$LogLines = 40
)

$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

function Get-ToolPath {
    param(
        [string]$Name,
        [string]$DefaultPath
    )

    if ($DefaultPath -and (Test-Path -LiteralPath $DefaultPath)) {
        return $DefaultPath
    }

    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    throw "$Name command was not found."
}

function Resolve-GcpHost {
    param(
        [string]$InstanceName,
        [string]$InstanceZone,
        [string]$ProjectId
    )

    $gcloud = Get-ToolPath `
        -Name "gcloud" `
        -DefaultPath (Join-Path $env:LOCALAPPDATA "Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd")

    $ip = & $gcloud compute instances describe $InstanceName `
        --zone $InstanceZone `
        --project $ProjectId `
        --format "value(networkInterfaces[0].accessConfigs[0].natIP)"

    if (-not $ip) {
        throw "Could not find an external IP for $InstanceName."
    }

    return $ip.Trim()
}

if (-not $HostName) {
    $HostName = Resolve-GcpHost -InstanceName $Instance -InstanceZone $Zone -ProjectId $Project
}

$ssh = Get-ToolPath -Name "ssh" -DefaultPath (Join-Path $env:WINDIR "System32\OpenSSH\ssh.exe")
$target = "$User@$HostName"
$safeRepoPath = $RepoPath.Replace("'", "'\''")
$safeLogLines = [Math]::Max(1, [Math]::Min($LogLines, 300))

$remoteCommand = @'
set -e
REPO_PATH='__REPO_PATH__'
REPO_PATH="${REPO_PATH/#\~/$HOME}"

echo "== VM =="
hostname
date
echo "target=__TARGET__"
echo "repo=$REPO_PATH"

echo
echo "== Server =="
if [ -x "$REPO_PATH/scripts/vm/server.sh" ]; then
  cd "$REPO_PATH"
  ./scripts/vm/server.sh status || true
else
  echo "server script not found: $REPO_PATH/scripts/vm/server.sh"
fi

echo
echo "== Daily Auto Cron =="
crontab -l 2>/dev/null | sed -n '/# hanstock-daily-auto begin/,/# hanstock-daily-auto end/p' || true

echo
echo "== Latest Daily Auto Log =="
if [ -f "$REPO_PATH/logs/daily-auto.log" ]; then
  tail -n __LOG_LINES__ "$REPO_PATH/logs/daily-auto.log"
else
  echo "daily-auto log not found"
fi
'@

$remoteCommand = $remoteCommand.
    Replace("__REPO_PATH__", $safeRepoPath).
    Replace("__TARGET__", $target).
    Replace("__LOG_LINES__", [string]$safeLogLines)

$remoteCommand = $remoteCommand -replace "`r`n", "`n" -replace "`r", "`n"
$encodedCommand = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($remoteCommand))

Write-Host "[vm-check] target: $target"
Write-Host "[vm-check] instance: $Instance"
Write-Host "[vm-check] repo: $RepoPath"

if (Test-Path -LiteralPath $KeyPath) {
    & $ssh -i $KeyPath -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 $target "echo $encodedCommand | base64 -d | bash"
} else {
    & $ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 $target "echo $encodedCommand | base64 -d | bash"
}

if ($LASTEXITCODE -ne 0) {
    throw "VM check failed with exit code $LASTEXITCODE"
}
