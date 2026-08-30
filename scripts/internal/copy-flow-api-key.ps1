param([string]$FlowAgentDir = "")

$ErrorActionPreference = "Stop"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$DataRoot = Join-Path $env:LOCALAPPDATA "ComfyUIFlowAgent"
$ConfigPath = Join-Path $DataRoot "flow-local.config.json"
$LegacyConfigPath = Join-Path (Split-Path -Parent $ScriptRoot) "flow-local.config.json"
if (-not (Test-Path -LiteralPath $ConfigPath) -and (Test-Path -LiteralPath $LegacyConfigPath)) {
    $ConfigPath = $LegacyConfigPath
}

if ([string]::IsNullOrWhiteSpace($FlowAgentDir)) {
    if (Test-Path -LiteralPath $ConfigPath -PathType Leaf) {
        $Config = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
        $FlowAgentDir = [string]$Config.flow_agent_dir
    }
}
if ([string]::IsNullOrWhiteSpace($FlowAgentDir)) {
    $DefaultFlowAgentDir = Join-Path $env:USERPROFILE "FlowAgent\flow-agent\flow-agent"
    if (Test-Path -LiteralPath $DefaultFlowAgentDir -PathType Container) {
        $FlowAgentDir = $DefaultFlowAgentDir
    }
}
if ([string]::IsNullOrWhiteSpace($FlowAgentDir)) {
    throw "Flow Agent was not found. Run 01-INSTALL-FLOW.cmd or provide -FlowAgentDir."
}

$EnvPath = Join-Path $FlowAgentDir ".env"
if (-not (Test-Path -LiteralPath $EnvPath -PathType Leaf)) {
    throw "Flow Agent configuration was not found: $EnvPath"
}

$Line = Get-Content -LiteralPath $EnvPath |
    Where-Object { $_ -match '^SERVER_API_KEY=' } |
    Select-Object -Last 1
if (-not $Line) {
    throw "SERVER_API_KEY is missing from $EnvPath"
}

$ApiKey = $Line.Split("=", 2)[1].Trim().Trim('"').Trim("'")
if ([string]::IsNullOrWhiteSpace($ApiKey)) {
    throw "SERVER_API_KEY is empty in $EnvPath"
}

$ApiKey | Set-Clipboard
Write-Host "The actual Flow Agent API key was copied to the clipboard without being displayed." -ForegroundColor Green
Write-Host "Paste it into the RunPod secret value for: flow_agent_api_key"
