param([int]$Port = 8001)

$ErrorActionPreference = "Stop"
try {
    $Health = Invoke-RestMethod "http://127.0.0.1:$Port/health" -TimeoutSec 5
    $Health | Format-List status, extension_connected, has_flow_key, transport
} catch {
    Write-Host "Flow Agent is not responding: $($_.Exception.Message)" -ForegroundColor Red
}

try {
    $Tunnels = Invoke-RestMethod "http://127.0.0.1:4040/api/tunnels" -TimeoutSec 3
    $Url = @(
        $Tunnels.tunnels | Where-Object {
            $_.proto -eq "https" -and $_.config.addr -match "(^|:)$Port$"
        }
    )[0].public_url
    Write-Host "ngrok: $Url"
} catch {
    Write-Host "ngrok is not responding." -ForegroundColor Red
}
