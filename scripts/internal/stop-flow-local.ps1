param([switch]$Elevated)

$ErrorActionPreference = "Stop"

$Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$Principal = New-Object Security.Principal.WindowsPrincipal($Identity)
$IsAdministrator = $Principal.IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)

if (-not $IsAdministrator) {
    if ($Elevated) {
        throw "Administrator permission was not granted to stop Flow Agent."
    }
    $Arguments = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", "`"$PSCommandPath`"",
        "-Elevated"
    )
    Start-Process powershell.exe -Verb RunAs -ArgumentList $Arguments
    Write-Host "Administrator permission was requested in another window."
    exit 0
}

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$DataRoot = Join-Path $env:LOCALAPPDATA "ComfyUIFlowAgent"
$ConfigPath = Join-Path $DataRoot "flow-local.config.json"
$StatePath = Join-Path $DataRoot "flow-local-state.json"
$LegacyStatePath = Join-Path (Split-Path -Parent $ScriptRoot) ".flow-local-state.json"
if (-not (Test-Path -LiteralPath $StatePath) -and (Test-Path -LiteralPath $LegacyStatePath)) {
    $StatePath = $LegacyStatePath
}

function Stop-ProcessTree([int]$RootProcessId) {
    $Children = Get-CimInstance Win32_Process -Filter "ParentProcessId=$RootProcessId" `
        -ErrorAction SilentlyContinue
    foreach ($Child in @($Children)) {
        Stop-ProcessTree -RootProcessId $Child.ProcessId
    }

    $Process = Get-Process -Id $RootProcessId -ErrorAction SilentlyContinue
    if ($Process) {
        $ProcessName = $Process.ProcessName
        # A parent such as uv can exit automatically when its Python child is
        # stopped. Ignore that harmless race and continue on to ngrok.
        Stop-Process -Id $RootProcessId -Force -ErrorAction SilentlyContinue
        if (-not (Get-Process -Id $RootProcessId -ErrorAction SilentlyContinue)) {
            Write-Host "Stopped process: $ProcessName ($RootProcessId)"
        }
    }
}

$Config = $null
if (Test-Path -LiteralPath $ConfigPath -PathType Leaf) {
    $Config = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
}
$FlowAgentDir = if ($Config -and $Config.flow_agent_dir) { [string]$Config.flow_agent_dir } else { "" }
$BackendPort = if ($Config -and $Config.port) { [int]$Config.port } else { 8001 }
$BridgePort = 9227
$EnvPath = if ($FlowAgentDir) { Join-Path $FlowAgentDir ".env" } else { "" }
if ($EnvPath -and (Test-Path -LiteralPath $EnvPath -PathType Leaf)) {
    $WsLine = Get-Content -LiteralPath $EnvPath |
        Where-Object { $_ -match '^WS_PORT=' } |
        Select-Object -Last 1
    if ($WsLine) {
        $ParsedBridgePort = 0
        if ([int]::TryParse($WsLine.Split('=', 2)[1].Trim().Trim('"').Trim("'"), [ref]$ParsedBridgePort)) {
            $BridgePort = $ParsedBridgePort
        }
    }
}

$State = $null
if (Test-Path -LiteralPath $StatePath -PathType Leaf) {
    $State = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
}

function Get-ProcessRecord([int]$ProcessId) {
    return Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" `
        -ErrorAction SilentlyContinue
}

function Test-ManagedFlowProcess($ProcessRecord) {
    if (-not $ProcessRecord) { return $false }
    $CommandLine = [string]$ProcessRecord.CommandLine
    $ExecutablePath = [string]$ProcessRecord.ExecutablePath
    if ($FlowAgentDir) {
        $ResolvedRoot = [IO.Path]::GetFullPath($FlowAgentDir).TrimEnd('\')
        if ($ExecutablePath.StartsWith($ResolvedRoot, [StringComparison]::OrdinalIgnoreCase)) {
            return $true
        }
        if ($CommandLine.IndexOf($ResolvedRoot, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
            return $true
        }
    }
    return $CommandLine -match '(?i)(uv\s+run\s+python\s+main\.py|python(?:\.exe)?[^\r\n]*\smain\.py)'
}

function Test-ManagedNgrokProcess($ProcessRecord) {
    if (-not $ProcessRecord) { return $false }
    $CommandLine = [string]$ProcessRecord.CommandLine
    return $ProcessRecord.Name -match '(?i)^ngrok(?:\.exe)?$' -and
        $CommandLine -match "(?i)\bhttp\b[^\r\n]*\b$BackendPort\b"
}

$Listeners = @(
    Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -in @($BackendPort, $BridgePort, 4040) }
)
$ManagedProcessIds = @()
if ($State -and $State.flow_pid) {
    $Process = Get-ProcessRecord -ProcessId ([int]$State.flow_pid)
    if (Test-ManagedFlowProcess $Process) { $ManagedProcessIds += [int]$State.flow_pid }
}
if ($State -and $State.ngrok_pid) {
    $Process = Get-ProcessRecord -ProcessId ([int]$State.ngrok_pid)
    if (Test-ManagedNgrokProcess $Process) { $ManagedProcessIds += [int]$State.ngrok_pid }
}
foreach ($Listener in $Listeners) {
    $Process = Get-ProcessRecord -ProcessId ([int]$Listener.OwningProcess)
    $IsManaged = if ($Listener.LocalPort -eq 4040) {
        Test-ManagedNgrokProcess $Process
    } else {
        Test-ManagedFlowProcess $Process
    }
    if ($IsManaged) {
        $ManagedProcessIds += [int]$Listener.OwningProcess
    } else {
        Write-Warning "Skipped unrelated process on port $($Listener.LocalPort), PID $($Listener.OwningProcess)."
    }
}
$ManagedProcessIds = @($ManagedProcessIds | Select-Object -Unique)

foreach ($ProcessId in $ManagedProcessIds) {
    if (-not $ProcessId) { continue }
    try {
        Stop-ProcessTree -RootProcessId $ProcessId
    } catch {
        Write-Warning "Process $ProcessId could not be stopped completely: $($_.Exception.Message)"
    }
}

$ShutdownDeadline = (Get-Date).AddSeconds(8)
do {
    $RemainingPorts = @(
        Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
            Where-Object { $_.LocalPort -in @($BackendPort, $BridgePort, 4040) } |
            Where-Object {
                $Process = Get-ProcessRecord -ProcessId ([int]$_.OwningProcess)
                if ($_.LocalPort -eq 4040) {
                    Test-ManagedNgrokProcess $Process
                } else {
                    Test-ManagedFlowProcess $Process
                }
            }
    )
    if ($RemainingPorts.Count -eq 0) { break }
    Start-Sleep -Milliseconds 250
} while ((Get-Date) -lt $ShutdownDeadline)

if ($RemainingPorts.Count -gt 0) {
    $Details = ($RemainingPorts | ForEach-Object {
        "port $($_.LocalPort), PID $($_.OwningProcess)"
    }) -join "; "
    throw "Some services are still active: $Details"
}

Remove-Item -LiteralPath $StatePath -ErrorAction SilentlyContinue
if ($ManagedProcessIds.Count -eq 0) {
    Write-Host "No managed Flow Agent or ngrok processes were running." -ForegroundColor Green
} else {
    Write-Host "Flow Agent, its extension bridge, and any managed ngrok tunnel have stopped." -ForegroundColor Green
}
