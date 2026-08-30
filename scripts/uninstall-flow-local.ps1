param(
    [switch]$Elevated,
    [switch]$Confirm
)

$ErrorActionPreference = "Stop"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ConfigPath = Join-Path $ScriptRoot "flow-local.config.json"
$StatePath = Join-Path $ScriptRoot ".flow-local-state.json"
$ShortcutPath = Join-Path ([Environment]::GetFolderPath("Desktop")) "INICIAR FLOW AGENT.lnk"

function Get-FullPath([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) { return "" }
    return [IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($Path)).TrimEnd('\')
}

function Stop-ManagedProcessTree([int]$RootProcessId, [string]$ExpectedKind) {
    $Root = Get-CimInstance Win32_Process -Filter "ProcessId=$RootProcessId" -ErrorAction SilentlyContinue
    if (-not $Root) { return }

    $Name = [string]$Root.Name
    $CommandLine = [string]$Root.CommandLine
    $MatchesExpectedProcess = if ($ExpectedKind -eq "ngrok") {
        $Name -match "^ngrok(\.exe)?$" -and $CommandLine -match "\shttp\s"
    } else {
        $Name -match "^(uv|python|python3)(\.exe)?$" -and $CommandLine -match "main\.py"
    }
    if (-not $MatchesExpectedProcess) {
        Write-Warning "Se conservo el PID $RootProcessId porque ya no parece pertenecer a $ExpectedKind."
        return
    }

    $Children = Get-CimInstance Win32_Process -Filter "ParentProcessId=$RootProcessId" -ErrorAction SilentlyContinue
    foreach ($Child in @($Children)) {
        Stop-Process -Id $Child.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Stop-Process -Id $RootProcessId -Force -ErrorAction SilentlyContinue
}

Write-Host "DESINSTALADOR LOCAL DE FLOW AGENT" -ForegroundColor Magenta
Write-Host ""
Write-Host "Se eliminaran solamente:" -ForegroundColor Yellow
Write-Host "  - La copia de Flow Agent creada por este instalador."
Write-Host "  - Los archivos privados dentro de esa copia, como .env, .venv, cache y salidas."
Write-Host "  - La configuracion, estado, logs y acceso directo de este proyecto."
Write-Host ""
Write-Host "Se conservaran:" -ForegroundColor Green
Write-Host "  - Google Chrome, sus perfiles, historial y cualquier dato del navegador."
Write-Host "  - La configuracion de extensiones dentro del navegador."
Write-Host "  - Los proyectos y archivos de Google Flow."
Write-Host "  - Python de Windows, entornos externos, paquetes y caches compartidas."
Write-Host "  - Git, uv, ngrok y la configuracion compartida de ngrok."
Write-Host "  - ComfyUI, sus modelos, workflows y archivos generados."
Write-Host ""

if (-not $Confirm) {
    $Answer = Read-Host "Escribe DESINSTALAR para continuar"
    if ($Answer -cne "DESINSTALAR") {
        Write-Host "Operacion cancelada. No se elimino nada."
        exit 0
    }
}

$Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$Principal = New-Object Security.Principal.WindowsPrincipal($Identity)
$IsAdministrator = $Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $IsAdministrator) {
    if ($Elevated) { throw "No se obtuvieron permisos para completar la desinstalacion." }
    $Arguments = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", "`"$PSCommandPath`"",
        "-Elevated",
        "-Confirm"
    )
    Start-Process powershell.exe -Verb RunAs -ArgumentList $Arguments -Wait
    exit 0
}

$Config = $null
if (Test-Path -LiteralPath $ConfigPath -PathType Leaf) {
    try {
        $Config = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
    } catch {
        Write-Warning "La configuracion local no es valida. Se conservara la carpeta de Flow Agent."
    }
}

if (Test-Path -LiteralPath $StatePath -PathType Leaf) {
    try {
        $State = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
        if ($State.flow_pid) { Stop-ManagedProcessTree -RootProcessId ([int]$State.flow_pid) -ExpectedKind "flow" }
        if ($State.ngrok_pid) { Stop-ManagedProcessTree -RootProcessId ([int]$State.ngrok_pid) -ExpectedKind "ngrok" }
    } catch {
        Write-Warning "No se pudieron detener todos los procesos registrados: $($_.Exception.Message)"
    }
}

$RemovedManagedRepository = $false
if ($Config -and $Config.managed_flow_repository -eq $true) {
    $InstallRoot = Get-FullPath ([string]$Config.install_root)
    $FlowRepoDir = Get-FullPath ([string]$Config.flow_repo_dir)
    $MarkerPath = Get-FullPath ([string]$Config.install_marker)
    $ExpectedRepoDir = if ($InstallRoot) { Get-FullPath (Join-Path $InstallRoot "flow-agent") } else { "" }

    $Marker = $null
    if ($MarkerPath -and (Test-Path -LiteralPath $MarkerPath -PathType Leaf)) {
        try { $Marker = Get-Content -LiteralPath $MarkerPath -Raw | ConvertFrom-Json } catch {}
    }
    $OwnershipVerified = (
        $InstallRoot -and
        $FlowRepoDir -and
        $FlowRepoDir -eq $ExpectedRepoDir -and
        $Marker -and
        $Marker.created_by -eq "comfyui-flow-agent" -and
        $Marker.install_id -eq $Config.install_id -and
        (Get-FullPath ([string]$Marker.flow_repo_dir)) -eq $FlowRepoDir
    )

    if ($OwnershipVerified) {
        if (Test-Path -LiteralPath $FlowRepoDir) {
            Remove-Item -LiteralPath $FlowRepoDir -Recurse -Force
            Write-Host "Eliminado: $FlowRepoDir"
        }
        Remove-Item -LiteralPath $MarkerPath -Force -ErrorAction SilentlyContinue
        if ((Test-Path -LiteralPath $InstallRoot) -and -not (Get-ChildItem -LiteralPath $InstallRoot -Force | Select-Object -First 1)) {
            Remove-Item -LiteralPath $InstallRoot -Force
        }
        $RemovedManagedRepository = $true
    } else {
        Write-Warning "No se pudo demostrar que la carpeta de Flow Agent fue creada por este instalador. Se conservo completa."
    }
} else {
    Write-Warning "La instalacion no tiene una marca de propiedad valida. La carpeta de Flow Agent se conservara."
}

if (Test-Path -LiteralPath $ShortcutPath -PathType Leaf) {
    try {
        $Shell = New-Object -ComObject WScript.Shell
        $Shortcut = $Shell.CreateShortcut($ShortcutPath)
        $ExpectedTarget = Get-FullPath (Join-Path $ScriptRoot "INICIAR-FLOW.cmd")
        if ((Get-FullPath $Shortcut.TargetPath) -eq $ExpectedTarget) {
            Remove-Item -LiteralPath $ShortcutPath -Force
        } else {
            Write-Warning "Se conservo el acceso directo porque pertenece a otro destino."
        }
    } catch {
        Write-Warning "No se pudo validar el acceso directo; se conservo."
    }
}

$LocalArtifacts = @(
    $StatePath,
    $ConfigPath,
    (Join-Path $ScriptRoot "flow-agent.stdout.log"),
    (Join-Path $ScriptRoot "flow-agent.stderr.log"),
    (Join-Path $ScriptRoot "ngrok.log")
)
foreach ($Artifact in $LocalArtifacts) {
    Remove-Item -LiteralPath $Artifact -Force -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "DESINSTALACION TERMINADA" -ForegroundColor Green
if (-not $RemovedManagedRepository) {
    Write-Host "La copia de Flow Agent se conservo por seguridad; no tenia una marca verificable del instalador." -ForegroundColor Yellow
}
Write-Host "Chrome y todos los datos personales del usuario permanecen intactos."
