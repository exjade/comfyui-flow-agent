param(
    [string]$FlowAgentDir = "",
    [string]$NgrokExe = "",
    [int]$Port = 0
)

$ErrorActionPreference = "Stop"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ConfigPath = Join-Path $ScriptRoot "flow-local.config.json"

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
            throw "Flow Agent was not found. Run scripts\INSTALL-FLOW.cmd or provide -FlowAgentDir."
        }
    }
}
if ([string]::IsNullOrWhiteSpace($NgrokExe)) {
    if ($LocalConfig -and $LocalConfig.ngrok_exe) {
        $NgrokExe = [string]$LocalConfig.ngrok_exe
    } else {
        $NgrokCommand = Get-Command ngrok -ErrorAction SilentlyContinue
        if (-not $NgrokCommand) {
            throw "ngrok was not found. Run scripts\INSTALL-FLOW.cmd or provide -NgrokExe."
        }
        $NgrokExe = $NgrokCommand.Source
    }
}
if ($Port -le 0) {
    $Port = if ($LocalConfig -and $LocalConfig.port) { [int]$LocalConfig.port } else { 8001 }
}

$StatePath = Join-Path $ScriptRoot ".flow-local-state.json"
$StdoutLog = Join-Path $ScriptRoot "flow-agent.stdout.log"
$StderrLog = Join-Path $ScriptRoot "flow-agent.stderr.log"
$NgrokLog = Join-Path $ScriptRoot "ngrok.log"
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

$ProjectId = Get-DotEnvValue "DEFAULT_PROJECT"
if ([string]::IsNullOrWhiteSpace($ProjectId)) {
    throw "Add DEFAULT_PROJECT=<project-id> to the Flow Agent .env file."
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

$FlowProcess = $null
$Health = $null
try { $Health = Invoke-RestMethod "http://127.0.0.1:$Port/health" -TimeoutSec 3 } catch {}

if ($Health -and $PreviousPublicUrl -eq $PublicUrl) {
    Write-Host "Flow Agent is already running with this tunnel."
} else {
    $Listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($Listener) {
        $Owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($Listener.OwningProcess)"
        if ($Owner.CommandLine -notmatch "main\.py") {
            throw "Port $Port is already used by another program: $($Owner.CommandLine)"
        }
        Stop-Process -Id $Listener.OwningProcess -Force
        Start-Sleep -Seconds 1
    }

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

$Deadline = (Get-Date).AddSeconds(45)
do {
    Start-Sleep -Milliseconds 750
    try { $Health = Invoke-RestMethod "http://127.0.0.1:$Port/health" -TimeoutSec 3 } catch { $Health = $null }
} while (-not $Health -and (Get-Date) -lt $Deadline)

if (-not $Health) {
    throw "Flow Agent did not respond. Check $StderrLog"
}

$ProjectUrl = "https://labs.google/fx/es-419/tools/flow/project/$ProjectId"
Start-Process $ProjectUrl
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
Write-Host "Paste the URL into FLOW_AGENT_BASE_URL on RunPod, then restart ComfyUI."
