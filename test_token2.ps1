Start-Sleep -Seconds 3
Write-Host "=== Test Token 2 ==="
try {
    $body = @{
        grant_type = "client_credentials"
        appkey = "PSRbHvDznFZ5hgMt79HSTZOkuD1pmpV6BbbE"
        appsecret = "3hN78gS1WxNguRJsgjkHQ3modvnhkT5oK9rtrh18GIACnZLlfsa/vsmH4sJGttlK8lRhHQrF/NJJqlLBgvvC+wuTJFw2mFMSZaA1bB5W8b642IsTicigXWbaIoUY1gLl9YtITvvR3jaS6ZTQB3ZQ/0az/PO0i8fEuW1hc2dOrKSOylLX+YY="
    } | ConvertTo-Json
    
    $result = Invoke-RestMethod -Uri "https://openapivts.koreainvestment.com:29443/oauth2/tokenP" -Method POST -Body $body -ContentType "application/json" -TimeoutSec 15
    $result | ConvertTo-Json -Depth 3
} catch {
    Write-Host "Error: $_"
}