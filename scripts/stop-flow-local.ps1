param([switch]$Elevated)

$ErrorActionPreference = "Stop"

$Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$Principal = New-Object Security.Principal.WindowsPrincipal($Identity)
$IsAdministrator = $Principal.IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)

if (-not $IsAdministrator) {
    if ($Elevated) {
        throw "No se obtuvieron permisos de administrador para detener Flow Agent."
    }
    $Arguments = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", "`"$PSCommandPath`"",
        "-Elevated"
    )
    Start-Process powershell.exe -Verb RunAs -ArgumentList $Arguments
    Write-Host "Se solicitó permiso de administrador en otra ventana."
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
            Write-Host "Proceso detenido: $ProcessName ($RootProcessId)"
        }
    }
}

if (-not (Test-Path -LiteralPath $StatePath)) {
    Write-Host "No existe estado de una ejecución automatizada."
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
        Write-Warning "No se pudo detener por completo el proceso $ProcessId`: $($_.Exception.Message)"
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
        "puerto $($_.LocalPort), PID $($_.OwningProcess)"
    }) -join "; "
    throw "Quedaron servicios activos: $Details"
}

Remove-Item -LiteralPath $StatePath -ErrorAction SilentlyContinue
Write-Host "Flow Agent y ngrok quedaron detenidos." -ForegroundColor Green
