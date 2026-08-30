$ErrorActionPreference = "Stop"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$StatePath = Join-Path $ScriptRoot ".flow-local-state.json"

if (-not (Test-Path -LiteralPath $StatePath)) {
    Write-Host "No existe estado de una ejecución automatizada."
    exit 0
}

$State = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
foreach ($ProcessId in @($State.flow_pid, $State.ngrok_pid)) {
    if (-not $ProcessId) { continue }
    $Process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($Process) {
        Stop-Process -Id $ProcessId
        Write-Host "Proceso detenido: $($Process.ProcessName) ($ProcessId)"
    }
}
Remove-Item -LiteralPath $StatePath

