$ErrorActionPreference = "Continue"
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

New-Item -ItemType Directory -Force -Path ".runtime" | Out-Null
$LogPath = Join-Path $Root ".runtime\signal_trader.log"

"$(Get-Date -Format o) signal trader start" | Out-File -FilePath $LogPath -Append -Encoding utf8
python -u signal_trader.py 2>&1 | Out-File -FilePath $LogPath -Append -Encoding utf8
"$(Get-Date -Format o) signal trader end exit=$LASTEXITCODE" | Out-File -FilePath $LogPath -Append -Encoding utf8
