param([int]$Port = 0) # Read-only service status for Local and RunPod modes.

$ErrorActionPreference = "Stop"
$DataRoot = Join-Path $env:LOCALAPPDATA "ComfyUIFlowAgent"
$ConfigPath = Join-Path $DataRoot "flow-local.config.json"
$StatePath = Join-Path $DataRoot "flow-local-state.json"
$Config = $null
$State = $null
if (Test-Path -LiteralPath $ConfigPath -PathType Leaf) {
    try { $Config = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json } catch {}
}
if (Test-Path -LiteralPath $StatePath -PathType Leaf) {
    try { $State = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json } catch {}
}
if ($Port -le 0) { $Port = if ($Config -and $Config.port) { [int]$Config.port } else { 8001 } }
$Mode = if ($State -and $State.mode) { [string]$State.mode } else { "unknown" }
$BaseUrl = if ($State -and $State.base_url) { [string]$State.base_url } else { "http://127.0.0.1:$Port" }

Write-Host "Mode: $Mode"
Write-Host "Base URL: $BaseUrl"
try {
    $Health = Invoke-RestMethod "http://127.0.0.1:$Port/health" -TimeoutSec 5
    $Health | Format-List status, extension_connected, has_flow_key, transport
} catch {
    Write-Host "Flow Agent is not responding: $($_.Exception.Message)" -ForegroundColor Red
}

if ($Mode -eq "runpod" -or ($State -and $State.public_url)) {
    try {
        $Tunnels = Invoke-RestMethod "http://127.0.0.1:4040/api/tunnels" -TimeoutSec 3
        $Url = @($Tunnels.tunnels | Where-Object { $_.proto -eq "https" -and $_.config.addr -match "(^|:)$Port$" })[0].public_url
        Write-Host "ngrok: $Url"
    } catch {
        Write-Host "ngrok is not responding for RunPod mode." -ForegroundColor Red
    }
} elseif ($Mode -eq "local") {
    $ConfiguredBaseUrl = [Environment]::GetEnvironmentVariable("FLOW_AGENT_BASE_URL", "User")
    $ConfiguredApiKey = [Environment]::GetEnvironmentVariable("FLOW_AGENT_API_KEY", "User")
    Write-Host "Windows local configuration: $($ConfiguredBaseUrl -eq $BaseUrl -and -not [string]::IsNullOrWhiteSpace($ConfiguredApiKey))"
    Write-Host "ngrok: not used in Local mode"
} else {
    Write-Host "Run one of the step 4 launchers to select Local or RunPod mode." -ForegroundColor Yellow
}
