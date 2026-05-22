# Signal Trader Scheduled Task Installer
# Windows 작업 스케줄러에 등록

$scriptPath = "C:\0.JOB\stock4\hanstockauto\signal_trader.py"
$taskName = "SignalTrader"
$logPath = "C:\0.JOB\stock4\hanstockauto\.runtime\signal_trader.log"

# 작업 스케줄러에 등록
$action = New-ScheduledTaskAction -Execute "python" -Argument $scriptPath -WorkingDirectory "C:\0.JOB\stock4\hanstockauto"
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 1) -RepetitionDuration (New-TimeSpan -Days 9999)

# Python 경로 찾기
$pythonPath = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $pythonPath) {
    $pythonPath = "C:\Users\turtl\AppData\Local\Packages\PythonSoftwareFoundation.Python.3.10_qbz5n2kfra8p0\LocalCache\local-packages\Python310\python.exe"
}

$action = New-ScheduledTaskAction -Execute $pythonPath -Argument $scriptPath -WorkingDirectory "C:\0.JOB\stock4\hanstockauto"

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Description "Telegram Signal to Mock Trading" -RunLevel Limited

Write-Host "=== Signal Trader Scheduled Task ==="
Write-Host "Task Name: $taskName"
Write-Host "Interval: Every 1 minute"
Write-Host ""
Write-Host "To check status:"
Write-Host "  Get-ScheduledTask -TaskName $taskName"
Write-Host ""
Write-Host "To start now:"
Write-Host "  Start-ScheduledTask -TaskName $taskName"
Write-Host ""
Write-Host "To stop:"
Write-Host "  Stop-ScheduledTask -TaskName $taskName"
Write-Host ""
Write-Host "To remove:"
Write-Host "  Unregister-ScheduledTask -TaskName $taskName -Confirm:`$false"