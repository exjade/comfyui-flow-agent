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
$StatePath = Join-Path $ScriptRoot ".flow-local-state.json"

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

if (-not (Test-Path -LiteralPath $StatePath)) {
    Write-Host "No automated-run state file exists."
    exit 0
}

$State = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
$ListenerProcessIds = @(
    Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -in @(8001, 4040) } |
        Select-Object -ExpandProperty OwningProcess
)
$ProcessIds = @($State.flow_pid, $State.ngrok_pid) + $ListenerProcessIds |
    Where-Object { $_ } |
    Select-Object -Unique

foreach ($ProcessId in $ProcessIds) {
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
            Where-Object { $_.LocalPort -in @(8001, 4040) }
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
Write-Host "Flow Agent and ngrok have stopped." -ForegroundColor Green
