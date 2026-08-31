param(
    [ValidateSet("RunPod", "Local")]
    [string]$Mode = "RunPod",
    [string]$FlowAgentDir = "",
    [string]$NgrokExe = "",
    [int]$Port = 0
)

$ErrorActionPreference = "Stop"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$DataRoot = Join-Path $env:LOCALAPPDATA "ComfyUIFlowAgent"
$ConfigPath = Join-Path $DataRoot "flow-local.config.json"
$StatePath = Join-Path $DataRoot "flow-local-state.json"
$LegacyRoot = Split-Path -Parent $ScriptRoot
$RepositoryRoot = Split-Path -Parent $LegacyRoot
New-Item -ItemType Directory -Path $DataRoot -Force | Out-Null

foreach ($LegacyName in @("flow-local.config.json", ".flow-local-state.json", "flow-agent.stdout.log", "flow-agent.stderr.log", "ngrok.log")) {
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
if ($Port -le 0) {
    $Port = if ($LocalConfig -and $LocalConfig.port) { [int]$LocalConfig.port } else { 8001 }
}

$StdoutLog = Join-Path $DataRoot "flow-agent.stdout.log"
$StderrLog = Join-Path $DataRoot "flow-agent.stderr.log"
$NgrokLog = Join-Path $DataRoot "ngrok.log"
$EnvPath = Join-Path $FlowAgentDir ".env"
if (-not (Test-Path -LiteralPath $EnvPath -PathType Leaf)) { throw "File not found: $EnvPath" }

$GitCommand = Get-Command git -ErrorAction SilentlyContinue
if (-not $GitCommand) {
    throw "Git was not found. Run scripts\01-INSTALL-FLOW.cmd again."
}
foreach ($PatchName in @("flow-agent-media-reuse.patch", "flow-agent-video-reference.patch")) {
    $PatchPath = Join-Path $RepositoryRoot "patches\$PatchName"
    if (-not (Test-Path -LiteralPath $PatchPath -PathType Leaf)) {
        throw "Required compatibility patch is missing: $PatchPath"
    }
    & $GitCommand.Source -C $FlowAgentDir apply --reverse --check --unidiff-zero $PatchPath 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Flow Agent compatibility fixes are not installed ($PatchName). Run scripts\06-STOP-FLOW.cmd, then scripts\01-INSTALL-FLOW.cmd, before starting Local or RunPod mode."
    }
}

function Get-DotEnvValue([string]$Name) {
    $Line = Get-Content -LiteralPath $EnvPath | Where-Object { $_ -match "^$([regex]::Escape($Name))=" } | Select-Object -Last 1
    if (-not $Line) { return "" }
    return $Line.Split("=", 2)[1].Trim().Trim('"').Trim("'")
}

function Set-DotEnvValue([string]$Name, [string]$Value) {
    $Lines = @(Get-Content -LiteralPath $EnvPath)
    $Replacement = "$Name=$Value"
    $Found = $false
    $Updated = foreach ($Line in $Lines) {
        if ($Line -match "^$([regex]::Escape($Name))=") { $Found = $true; $Replacement } else { $Line }
    }
    if (-not $Found) { $Updated += $Replacement }
    $Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllLines($EnvPath, [string[]]$Updated, $Utf8NoBom)
}

function Import-DotEnvForChildProcess {
    foreach ($Line in Get-Content -LiteralPath $EnvPath) {
        $Trimmed = $Line.Trim()
        if (-not $Trimmed -or $Trimmed.StartsWith("#") -or -not $Trimmed.Contains("=")) { continue }
        $Parts = $Trimmed.Split("=", 2)
        $Name = $Parts[0].Trim()
        $Value = $Parts[1].Trim().Trim('"').Trim("'")
        if ($Name -match '^[A-Za-z_][A-Za-z0-9_]*$') { [Environment]::SetEnvironmentVariable($Name, $Value, "Process") }
    }
}

function Get-HttpStatus([string]$Url, [string]$BearerToken) {
    try {
        $Headers = @{}
        if (-not [string]::IsNullOrWhiteSpace($BearerToken)) { $Headers.Authorization = "Bearer $BearerToken" }
        $Response = Invoke-WebRequest -Uri $Url -Headers $Headers -TimeoutSec 5 -UseBasicParsing
        return [int]$Response.StatusCode
    } catch {
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) { return [int]$_.Exception.Response.StatusCode }
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
    return Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
}

function Test-ManagedFlowProcess($ProcessRecord) {
    if (-not $ProcessRecord) { return $false }
    $CommandLine = [string]$ProcessRecord.CommandLine
    $ExecutablePath = [string]$ProcessRecord.ExecutablePath
    $ResolvedRoot = [IO.Path]::GetFullPath($FlowAgentDir).TrimEnd('\')
    if ($ExecutablePath.StartsWith($ResolvedRoot, [StringComparison]::OrdinalIgnoreCase)) { return $true }
    if ($CommandLine.IndexOf($ResolvedRoot, [StringComparison]::OrdinalIgnoreCase) -ge 0) { return $true }
    return $CommandLine -match '(?i)(uv\s+run\s+python\s+main\.py|python(?:\.exe)?[^\r\n]*\smain\.py)'
}

function Test-ManagedNgrokProcess($ProcessRecord) {
    if (-not $ProcessRecord) { return $false }
    $CommandLine = [string]$ProcessRecord.CommandLine
    return $ProcessRecord.Name -match '(?i)^ngrok(?:\.exe)?$' -and $CommandLine -match "(?i)\bhttp\b[^\r\n]*\b$Port\b"
}

function Stop-ManagedListener([int]$ListenerPort) {
    $Listener = Get-NetTCPConnection -LocalPort $ListenerPort -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $Listener) { return }
    $Owner = Get-ProcessRecord -ProcessId ([int]$Listener.OwningProcess)
    if (-not (Test-ManagedFlowProcess $Owner)) { throw "Port $ListenerPort is already used by another program: $($Owner.CommandLine)" }
    Write-Host "Stopping stale Flow Agent listener on port $ListenerPort (PID $($Listener.OwningProcess))." -ForegroundColor Yellow
    Stop-Process -Id $Listener.OwningProcess -Force -ErrorAction SilentlyContinue
}

function Stop-ManagedNgrokTunnel {
    $Listener = Get-NetTCPConnection -LocalPort 4040 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $Listener) { return }
    $Owner = Get-ProcessRecord -ProcessId ([int]$Listener.OwningProcess)
    if (Test-ManagedNgrokProcess $Owner) {
        Write-Host "Stopping the RunPod ngrok tunnel because Local mode does not need it." -ForegroundColor Yellow
        Stop-Process -Id $Listener.OwningProcess -Force -ErrorAction SilentlyContinue
    }
}

$ProjectId = Get-DotEnvValue "DEFAULT_PROJECT"
if ([string]::IsNullOrWhiteSpace($ProjectId)) { throw "Add DEFAULT_PROJECT=<project-id> to the Flow Agent .env file." }
$BridgePortText = Get-DotEnvValue "WS_PORT"
$BridgePort = 9227
if (-not [string]::IsNullOrWhiteSpace($BridgePortText)) {
    $ParsedBridgePort = 0
    if (-not [int]::TryParse($BridgePortText, [ref]$ParsedBridgePort)) { throw "WS_PORT must be an integer; received '$BridgePortText'." }
    $BridgePort = $ParsedBridgePort
}

$NgrokProcess = $null
if ($Mode -eq "RunPod") {
    if ([string]::IsNullOrWhiteSpace($NgrokExe)) {
        if ($LocalConfig -and $LocalConfig.ngrok_exe) { $NgrokExe = [string]$LocalConfig.ngrok_exe } else {
            $NgrokCommand = Get-Command ngrok -ErrorAction SilentlyContinue
            if (-not $NgrokCommand) { throw "ngrok was not found. Run scripts\01-INSTALL-FLOW.cmd or provide -NgrokExe." }
            $NgrokExe = $NgrokCommand.Source
        }
    }
    if (Test-Path -LiteralPath $NgrokExe -PathType Leaf) {
        $NgrokExecutable = (Resolve-Path -LiteralPath $NgrokExe).Path
    } else {
        $NgrokCommand = Get-Command ngrok -ErrorAction SilentlyContinue
        if (-not $NgrokCommand) { throw "ngrok.exe was not found at '$NgrokExe' or in PATH." }
        $NgrokExecutable = $NgrokCommand.Source
    }

    try { $TunnelData = Invoke-RestMethod "http://127.0.0.1:4040/api/tunnels" -TimeoutSec 2 } catch {
        $NgrokProcess = Start-Process -FilePath $NgrokExecutable -ArgumentList @("http", "$Port", "--log=$NgrokLog", "--log-format=json") -WindowStyle Hidden -PassThru
        $TunnelData = $null
    }
    $Deadline = (Get-Date).AddSeconds(30)
    $PublicUrl = $null
    while (-not $PublicUrl -and (Get-Date) -lt $Deadline) {
        if ($TunnelData) {
            $MatchingTunnel = @($TunnelData.tunnels | Where-Object { $_.proto -eq "https" -and $_.config.addr -match "(^|:)$Port$" }) | Select-Object -First 1
            if ($MatchingTunnel) { $PublicUrl = $MatchingTunnel.public_url }
        }
        if ($PublicUrl) { break }
        Start-Sleep -Milliseconds 500
        try { $TunnelData = Invoke-RestMethod "http://127.0.0.1:4040/api/tunnels" -TimeoutSec 2 } catch { $TunnelData = $null }
    }
    if ([string]::IsNullOrWhiteSpace($PublicUrl)) { throw "ngrok did not provide an HTTPS tunnel. Check $NgrokLog" }
    $BaseUrl = $PublicUrl.TrimEnd("/")
} else {
    Stop-ManagedNgrokTunnel
    $BaseUrl = "http://127.0.0.1:$Port"
}

$PreviousBaseUrl = Get-DotEnvValue "PUBLIC_BASE_URL"
Set-DotEnvValue "PUBLIC_BASE_URL" $BaseUrl
$CurrentApiKey = Get-DotEnvValue "SERVER_API_KEY"
if ([string]::IsNullOrWhiteSpace($CurrentApiKey)) { throw "SERVER_API_KEY is empty in $EnvPath. Run scripts\01-INSTALL-FLOW.cmd again." }
Import-DotEnvForChildProcess

if ($Mode -eq "Local") {
    [Environment]::SetEnvironmentVariable("FLOW_AGENT_BASE_URL", $BaseUrl, "User")
    [Environment]::SetEnvironmentVariable("FLOW_AGENT_API_KEY", $CurrentApiKey, "User")
    [Environment]::SetEnvironmentVariable("FLOW_AGENT_BASE_URL", $BaseUrl, "Process")
    [Environment]::SetEnvironmentVariable("FLOW_AGENT_API_KEY", $CurrentApiKey, "Process")
}

$FlowProcess = $null
$Health = $null
try { $Health = Invoke-RestMethod "http://127.0.0.1:$Port/health" -TimeoutSec 3 } catch {}
$BackendAcceptsCurrentKey = if ($Health) { Test-BackendApiKey -BackendPort $Port -ExpectedKey $CurrentApiKey } else { $false }
if ($Health -and $PreviousBaseUrl -eq $BaseUrl -and $BackendAcceptsCurrentKey) {
    Write-Host "Flow Agent is already running in $Mode mode."
} else {
    if ($Health -and -not $BackendAcceptsCurrentKey) {
        Write-Host "The running backend uses different authentication settings and will be restarted." -ForegroundColor Yellow
    } elseif ($Health -and $PreviousBaseUrl -ne $BaseUrl) {
        Write-Host "Switching Flow Agent from '$PreviousBaseUrl' to '$BaseUrl'." -ForegroundColor Yellow
    }
    foreach ($ListenerPort in @($Port, $BridgePort) | Select-Object -Unique) { Stop-ManagedListener -ListenerPort $ListenerPort }
    Start-Sleep -Seconds 1
    $UvCommand = Get-Command uv -ErrorAction Stop
    $FlowProcess = Start-Process -FilePath $UvCommand.Source -ArgumentList @("run", "python", "main.py") -WorkingDirectory $FlowAgentDir -WindowStyle Hidden -RedirectStandardOutput $StdoutLog -RedirectStandardError $StderrLog -PassThru
}

$ProjectUrl = "https://labs.google/fx/es-419/tools/flow/project/$ProjectId"
Start-Process $ProjectUrl
$Deadline = (Get-Date).AddSeconds(45)
do {
    Start-Sleep -Milliseconds 750
    try { $Health = Invoke-RestMethod "http://127.0.0.1:$Port/health" -TimeoutSec 3 } catch { $Health = $null }
    $IsReady = ($Health -and $Health.status -eq "healthy" -and $Health.extension_connected -eq $true -and $Health.has_flow_key -eq $true)
} while (-not $IsReady -and (Get-Date) -lt $Deadline)

if (-not $Health) { throw "Flow Agent did not respond. Check $StderrLog" }
if (-not $IsReady) {
    $LauncherName = if ($Mode -eq "Local") { "04.1-START-FLOW-LOCAL.cmd" } else { "04-START-FLOW-RUNPOD.cmd" }
    throw "Flow Agent started, but the Chrome extension is not ready. Open the configured Flow project, confirm that the extension is ON, refresh its token, and run $LauncherName again."
}

$BaseUrl | Set-Clipboard
$State = [ordered]@{
    mode = $Mode.ToLowerInvariant()
    base_url = $BaseUrl
    public_url = if ($Mode -eq "RunPod") { $BaseUrl } else { $null }
    project_id = $ProjectId
    flow_pid = if ($FlowProcess) { $FlowProcess.Id } else { $null }
    ngrok_pid = if ($NgrokProcess) { $NgrokProcess.Id } else { $null }
    started_at = (Get-Date).ToString("o")
}
$State | ConvertTo-Json | Set-Content -LiteralPath $StatePath -Encoding utf8

Write-Host ""
Write-Host "READY - $Mode MODE" -ForegroundColor Green
Write-Host "Base URL copied to the clipboard: $BaseUrl" -ForegroundColor Cyan
Write-Host "Project opened: $ProjectUrl"
Write-Host "Flow Agent status: $($Health.status)"
Write-Host ""
if ($Mode -eq "RunPod") {
    Write-Host "REQUIRED RUNPOD ENVIRONMENT VARIABLES" -ForegroundColor Yellow
    Write-Host "Key:   FLOW_AGENT_BASE_URL"
    Write-Host "Value: $BaseUrl"
    Write-Host ""
    Write-Host "Key:   FLOW_AGENT_API_KEY"
    Write-Host 'Value: {{ RUNPOD_SECRET_flow_agent_api_key }}'
    Write-Host ""
    Write-Host "Save both variables in the Pod settings, then restart the Pod or ComfyUI."
} else {
    Write-Host "LOCAL COMFYUI CONFIGURATION" -ForegroundColor Yellow
    Write-Host "FLOW_AGENT_BASE_URL was configured as $BaseUrl for your Windows user."
    Write-Host "FLOW_AGENT_API_KEY was configured securely without displaying it."
    Write-Host "Fully close and reopen ComfyUI Desktop so it reads the new variables." -ForegroundColor Cyan
    Write-Host "No ngrok tunnel is used in Local mode."
}
