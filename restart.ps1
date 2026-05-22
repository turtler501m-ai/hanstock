$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = $ScriptDir
$RuntimeDir = Join-Path $RootDir ".runtime"
$PidFile = Join-Path $RuntimeDir "dashboard-server.pid"
$StdoutLog = Join-Path $RuntimeDir "dashboard-server.log"
$StderrLog = Join-Path $RuntimeDir "dashboard-server.err.log"

function Find-Python {
    if ($env:PYTHON) {
        return $env:PYTHON
    }

    $Candidates = @(
        (Join-Path $RootDir ".venv\Scripts\python.exe"),
        (Join-Path $RootDir "venv\Scripts\python.exe"),
        "python3",
        "python"
    )

    foreach ($candidate in $Candidates) {
        if ($candidate -match "python[0-9]*$") {
            $python = Get-Command $candidate -ErrorAction SilentlyContinue
            if ($python) {
                return $python.Source
            }
        } elseif (Test-Path $candidate) {
            return $candidate
        }
    }

    Write-Host "[restart] python executable not found" -ForegroundColor Red
    return $null
}

function Get-ListeningPids {
    $connections = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
    if ($connections) {
        return $connections | Select-Object -ExpandProperty OwningProcess -Unique
    }
    return @()
}

function Get-DashboardPids {
    $processes = Get-Process -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -like "*uvicorn*" -and $_.CommandLine -like "*src.dashboard*"
    }
    if ($processes) {
        return $processes | Select-Object -ExpandProperty Id -Unique
    }
    return @()
}

function Get-PidFilePids {
    if (Test-Path $PidFile) {
        $content = Get-Content $PidFile -ErrorAction SilentlyContinue
        if ($content -match "^\d+$") {
            return @([int]$content)
        }
    }
    return @()
}

function Get-ServerPids {
    $pids = @()
    $pids += Get-PidFilePids
    $pids += Get-ListeningPids
    $pids += Get-DashboardPids
    return ($pids | Sort-Object -Unique)
}

Write-Host "[restart] stopping existing server on port 8000..." -ForegroundColor Yellow

$serverPids = Get-ServerPids

if ($serverPids.Count -gt 0) {
    foreach ($processId in $serverPids) {
        try {
            $process = Get-Process -Id $processId -ErrorAction Stop
            Stop-Process -Id $processId -Force -ErrorAction Stop
            Write-Host "[restart] stopped PID $processId" -ForegroundColor Green
        } catch {
            Write-Host "[restart] could not stop PID $processId" -ForegroundColor Yellow
        }
    }
} else {
    Write-Host "[restart] no running server found" -ForegroundColor Gray
}

if (Test-Path $PidFile) {
    Remove-Item $PidFile -Force
}

for ($i = 0; $i -lt 5; $i++) {
    $listeningPids = Get-ListeningPids
    if ($listeningPids.Count -eq 0) {
        break
    }
    Start-Sleep -Seconds 1
}

$python = Find-Python
if (-not $python) {
    exit 1
}

Write-Host "[restart] starting server -- http://127.0.0.1:8000" -ForegroundColor Green

& $python -m uvicorn src.dashboard:app --reload --host 127.0.0.1 --port 8000