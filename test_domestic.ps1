Write-Host "=== Test Domestic Stock Balance ==="
$result = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/balance" -TimeoutSec 15
$result | ConvertTo-Json -Depth 3