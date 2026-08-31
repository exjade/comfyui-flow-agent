param(
    [string]$FlowAgentDir = "",
    [string]$NgrokExe = "",
    [int]$Port = 0
)

$ErrorActionPreference = "Stop"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$DataRoot = Join-Path $env:LOCALAPPDATA "ComfyUIFlowAgent"
$ConfigPath = Join-Path $DataRoot "flow-local.config.json"
$LegacyRoot = Split-Path -Parent $ScriptRoot
$LegacyConfigPath = Join-Path $LegacyRoot "flow-local.config.json"
New-Item -ItemType Directory -Path $DataRoot -Force | Out-Null
foreach ($LegacyName in @(
    "flow-local.config.json",
    ".flow-local-state.json",
    "flow-agent.stdout.log",
    "flow-agent.stderr.log",
    "ngrok.log"
)) {
    $LegacyPath = Join-Path $LegacyRoot $LegacyName
    $NewName = if ($LegacyName -eq ".flow-local-state.json") { "flow-local-state.json" } else { $LegacyName }
    $NewPath = Join-Path $DataRoot $NewName
    if ((Test-Path -LiteralPath $LegacyPath) -and -not (Test-Path -LiteralPath $NewPath)) {
        Move-Item -LiteralPath $LegacyPath -Destination $NewPath -ErrorAction SilentlyContinue
    }
}

$LocalConfig = $null
if (Test-Path -LiteralPath $ConfigPath -PathType Leaf) {
    $LocalConfig = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
}
if ([string]::IsNullOrWhiteSpace($FlowAgentDir)) {
    if ($LocalConfig -and $LocalConfig.flow_agent_dir) {
        $FlowAgentDir = [string]$LocalConfig.flow_agent_dir
    } else {
        $DefaultFlowAgentDir = Join-Path $env:USERPROFILE "FlowAgent\flow-agent\flow-agent"
        if (Test-Path -LiteralPath (Join-Path $DefaultFlowAgentDir ".env") -PathType Leaf) {
            $FlowAgentDir = $DefaultFlowAgentDir
        } else {
            throw "Flow Agent was not found. Run scripts\01-INSTALL-FLOW.cmd or provide -FlowAgentDir."
        }
    }
}
if ([string]::IsNullOrWhiteSpace($NgrokExe)) {
    if ($LocalConfig -and $LocalConfig.ngrok_exe) {
        $NgrokExe = [string]$LocalConfig.ngrok_exe
    } else {
        $NgrokCommand = Get-Command ngrok -ErrorAction SilentlyContinue
        if (-not $NgrokCommand) {
            throw "ngrok was not found. Run scripts\01-INSTALL-FLOW.cmd or provide -NgrokExe."
        }
        $NgrokExe = $NgrokCommand.Source
    }
}
if ($Port -le 0) {
    $Port = if ($LocalConfig -and $LocalConfig.port) { [int]$LocalConfig.port } else { 8001 }
}

$StatePath = Join-Path $DataRoot "flow-local-state.json"
$StdoutLog = Join-Path $DataRoot "flow-agent.stdout.log"
$StderrLog = Join-Path $DataRoot "flow-agent.stderr.log"
$NgrokLog = Join-Path $DataRoot "ngrok.log"
$EnvPath = Join-Path $FlowAgentDir ".env"

if (-not (Test-Path -LiteralPath $EnvPath)) {
    throw "File not found: $EnvPath"
}

function Get-DotEnvValue([string]$Name) {
    $line = Get-Content -LiteralPath $EnvPath | Where-Object { $_ -match "^$([regex]::Escape($Name))=" } | Select-Object -Last 1
    if (-not $line) { return "" }
    return $line.Split("=", 2)[1].Trim().Trim('"').Trim("'")
}

function Set-DotEnvValue([string]$Name, [string]$Value) {
    $lines = @(Get-Content -LiteralPath $EnvPath)
    $replacement = "$Name=$Value"
    $found = $false
    $updated = foreach ($line in $lines) {
        if ($line -match "^$([regex]::Escape($Name))=") {
            $found = $true
            $replacement
        } else {
            $line
        }
    }
    if (-not $found) { $updated += $replacement }
    $Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllLines($EnvPath, [string[]]$updated, $Utf8NoBom)
}

function Import-DotEnvForChildProcess {
    foreach ($Line in Get-Content -LiteralPath $EnvPath) {
        $Trimmed = $Line.Trim()
        if (-not $Trimmed -or $Trimmed.StartsWith("#") -or -not $Trimmed.Contains("=")) { continue }
        $Parts = $Trimmed.Split("=", 2)
        $Name = $Parts[0].Trim()
        $Value = $Parts[1].Trim().Trim('"').Trim("'")
        if ($Name -match '^[A-Za-z_][A-Za-z0-9_]*$') {
            [Environment]::SetEnvironmentVariable($Name, $Value, "Process")
        }
    }
}

function Get-HttpStatus([string]$Url, [string]$BearerToken) {
    try {
        $Headers = @{}
        if (-not [string]::IsNullOrWhiteSpace($BearerToken)) {
            $Headers.Authorization = "Bearer $BearerToken"
        }
        $Response = Invoke-WebRequest -Uri $Url -Headers $Headers -TimeoutSec 5 -UseBasicParsing
        return [int]$Response.StatusCode
    } catch {
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            return [int]$_.Exception.Response.StatusCode
        }
        return 0
    }
}

function Test-BackendApiKey([int]$BackendPort, [string]$ExpectedKey) {
    if ([string]::IsNullOrWhiteSpace($ExpectedKey)) { return $false }
    $ModelsUrl = "http://127.0.0.1:$BackendPort/v1/models"
    $CorrectStatus = Get-HttpStatus -Url $ModelsUrl -BearerToken $ExpectedKey
    $WrongStatus = Get-HttpStatus -Url $ModelsUrl -BearerToken "invalid-key-$([guid]::NewGuid().ToString('N'))"
    return $CorrectStatus -eq 200 -and $WrongStatus -eq 401
}

function Get-ProcessRecord([int]$ProcessId) {
    return Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" `
        -ErrorAction SilentlyContinue
}

function Test-ManagedFlowProcess($ProcessRecord) {
    if (-not $ProcessRecord) { return $false }
    $CommandLine = [string]$ProcessRecord.CommandLine
    $ExecutablePath = [string]$ProcessRecord.ExecutablePath
    $ResolvedRoot = [IO.Path]::GetFullPath($FlowAgentDir).TrimEnd('\')
    if ($ExecutablePath.StartsWith($ResolvedRoot, [StringComparison]::OrdinalIgnoreCase)) {
        return $true
    }
    if ($CommandLine.IndexOf($ResolvedRoot, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
        return $true
    }
    return $CommandLine -match '(?i)(uv\s+run\s+python\s+main\.py|python(?:\.exe)?[^\r\n]*\smain\.py)'
}

function Stop-ManagedListener([int]$ListenerPort) {
    $Listener = Get-NetTCPConnection -LocalPort $ListenerPort -State Listen `
        -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $Listener) { return }
    $Owner = Get-ProcessRecord -ProcessId ([int]$Listener.OwningProcess)
    if (-not (Test-ManagedFlowProcess $Owner)) {
        throw "Port $ListenerPort is already used by another program: $($Owner.CommandLine)"
    }
    Write-Host "Stopping stale Flow Agent listener on port $ListenerPort (PID $($Listener.OwningProcess))." -ForegroundColor Yellow
    Stop-Process -Id $Listener.OwningProcess -Force -ErrorAction SilentlyContinue
}

$ProjectId = Get-DotEnvValue "DEFAULT_PROJECT"
if ([string]::IsNullOrWhiteSpace($ProjectId)) {
    throw "Add DEFAULT_PROJECT=<project-id> to the Flow Agent .env file."
}
$BridgePortText = Get-DotEnvValue "WS_PORT"
$BridgePort = 9227
if (-not [string]::IsNullOrWhiteSpace($BridgePortText)) {
    $ParsedBridgePort = 0
    if (-not [int]::TryParse($BridgePortText, [ref]$ParsedBridgePort)) {
        throw "WS_PORT must be an integer; received '$BridgePortText'."
    }
    $BridgePort = $ParsedBridgePort
}

if (Test-Path -LiteralPath $NgrokExe -PathType Leaf) {
    $NgrokExecutable = (Resolve-Path -LiteralPath $NgrokExe).Path
} else {
    $NgrokCommand = Get-Command ngrok -ErrorAction SilentlyContinue
    if (-not $NgrokCommand) {
        throw "ngrok.exe was not found at '$NgrokExe' or in PATH."
    }
    $NgrokExecutable = $NgrokCommand.Source
}
$NgrokProcess = $null

try {
    $TunnelData = Invoke-RestMethod "http://127.0.0.1:4040/api/tunnels" -TimeoutSec 2
} catch {
    $NgrokProcess = Start-Process `
        -FilePath $NgrokExecutable `
        -ArgumentList @("http", "$Port", "--log=$NgrokLog", "--log-format=json") `
        -WindowStyle Hidden `
        -PassThru
    $TunnelData = $null
}

$Deadline = (Get-Date).AddSeconds(30)
$PublicUrl = $null
while (-not $PublicUrl -and (Get-Date) -lt $Deadline) {
    if ($TunnelData) {
        $MatchingTunnel = @(
            $TunnelData.tunnels | Where-Object {
                $_.proto -eq "https" -and $_.config.addr -match "(^|:)$Port$"
            }
        ) | Select-Object -First 1
        if ($MatchingTunnel) { $PublicUrl = $MatchingTunnel.public_url }
    }
    if ($PublicUrl) { break }
    Start-Sleep -Milliseconds 500
    try {
        $TunnelData = Invoke-RestMethod "http://127.0.0.1:4040/api/tunnels" -TimeoutSec 2
    } catch {
        $TunnelData = $null
    }
}

if ([string]::IsNullOrWhiteSpace($PublicUrl)) {
    throw "ngrok did not provide an HTTPS tunnel. Check $NgrokLog"
}
$PublicUrl = $PublicUrl.TrimEnd("/")

$PreviousPublicUrl = Get-DotEnvValue "PUBLIC_BASE_URL"
Set-DotEnvValue "PUBLIC_BASE_URL" $PublicUrl
$CurrentApiKey = Get-DotEnvValue "SERVER_API_KEY"
Import-DotEnvForChildProcess

$FlowProcess = $null
$Health = $null
try { $Health = Invoke-RestMethod "http://127.0.0.1:$Port/health" -TimeoutSec 3 } catch {}
$BackendAcceptsCurrentKey = if ($Health) {
    Test-BackendApiKey -BackendPort $Port -ExpectedKey $CurrentApiKey
} else {
    $false
}

if ($Health -and $PreviousPublicUrl -eq $PublicUrl -and $BackendAcceptsCurrentKey) {
    Write-Host "Flow Agent is already running with this tunnel."
} else {
    if ($Health -and -not $BackendAcceptsCurrentKey) {
        Write-Host "The running backend uses different authentication settings and will be restarted." -ForegroundColor Yellow
    }
    foreach ($ListenerPort in @($Port, $BridgePort) | Select-Object -Unique) {
        Stop-ManagedListener -ListenerPort $ListenerPort
    }
    Start-Sleep -Seconds 1

    $UvCommand = Get-Command uv -ErrorAction Stop
    $FlowProcess = Start-Process `
        -FilePath $UvCommand.Source `
        -ArgumentList @("run", "python", "main.py") `
        -WorkingDirectory $FlowAgentDir `
        -WindowStyle Hidden `
        -RedirectStandardOutput $StdoutLog `
        -RedirectStandardError $StderrLog `
        -PassThru
}

$ProjectUrl = "https://labs.google/fx/es-419/tools/flow/project/$ProjectId"
Start-Process $ProjectUrl

$Deadline = (Get-Date).AddSeconds(45)
do {
    Start-Sleep -Milliseconds 750
    try { $Health = Invoke-RestMethod "http://127.0.0.1:$Port/health" -TimeoutSec 3 } catch { $Health = $null }
    $IsReady = (
        $Health -and
        $Health.status -eq "healthy" -and
        $Health.extension_connected -eq $true -and
        $Health.has_flow_key -eq $true
    )
} while (-not $IsReady -and (Get-Date) -lt $Deadline)

if (-not $Health) {
    throw "Flow Agent did not respond. Check $StderrLog"
}
if (-not $IsReady) {
    throw "Flow Agent started, but the Chrome extension is not ready. Open the configured Flow project, confirm that the extension is ON, refresh its token, and run 04-START-FLOW.cmd again."
}

$PublicUrl | Set-Clipboard

$State = [ordered]@{
    public_url = $PublicUrl
    project_id = $ProjectId
    flow_pid = if ($FlowProcess) { $FlowProcess.Id } else { $null }
    ngrok_pid = if ($NgrokProcess) { $NgrokProcess.Id } else { $null }
    started_at = (Get-Date).ToString("o")
}
$State | ConvertTo-Json | Set-Content -LiteralPath $StatePath -Encoding utf8

Write-Host ""
Write-Host "READY" -ForegroundColor Green
Write-Host "URL copied to the clipboard: $PublicUrl" -ForegroundColor Cyan
Write-Host "Project opened: $ProjectUrl"
Write-Host "Local status: $($Health.status)"
Write-Host ""
Write-Host "REQUIRED RUNPOD ENVIRONMENT VARIABLES" -ForegroundColor Yellow
Write-Host "Key:   FLOW_AGENT_BASE_URL"
Write-Host "Value: $PublicUrl"
Write-Host ""
Write-Host "Key:   FLOW_AGENT_API_KEY"
Write-Host 'Value: {{ RUNPOD_SECRET_flow_agent_api_key }}'
Write-Host ""
Write-Host "Save both variables in the Pod settings, then restart the Pod or ComfyUI."
