Write-Host "=== Test Futures Balance API ==="
try {
    $result = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/futures/balance" -TimeoutSec 15
    $result | ConvertTo-Json -Depth 3
} catch {
    Write-Host "Error: $_"
}

Write-Host "`n=== Test Futures Positions API ==="
try {
    $result = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/futures/positions" -TimeoutSec 15
    $result | ConvertTo-Json -Depth 3
} catch {
    Write-Host "Error: $_"
}