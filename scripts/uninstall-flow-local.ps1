param(
    [switch]$Elevated,
    [switch]$Confirm
)

$ErrorActionPreference = "Stop"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ConfigPath = Join-Path $ScriptRoot "flow-local.config.json"
$StatePath = Join-Path $ScriptRoot ".flow-local-state.json"
$ShortcutPath = Join-Path ([Environment]::GetFolderPath("Desktop")) "START FLOW AGENT.lnk"

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
        Write-Warning "PID $RootProcessId was preserved because it no longer appears to belong to $ExpectedKind."
        return
    }

    $Children = Get-CimInstance Win32_Process -Filter "ParentProcessId=$RootProcessId" -ErrorAction SilentlyContinue
    foreach ($Child in @($Children)) {
        Stop-Process -Id $Child.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Stop-Process -Id $RootProcessId -Force -ErrorAction SilentlyContinue
}

Write-Host "FLOW AGENT LOCAL UNINSTALLER" -ForegroundColor Magenta
Write-Host ""
Write-Host "Only the following items will be removed:" -ForegroundColor Yellow
Write-Host "  - The Flow Agent copy created by this installer."
Write-Host "  - Private files inside that copy, including .env, .venv, cache, and outputs."
Write-Host "  - This project's configuration, state, logs, and desktop shortcut."
Write-Host ""
Write-Host "The following items will be preserved:" -ForegroundColor Green
Write-Host "  - Google Chrome, its profiles, history, and all browser data."
Write-Host "  - Browser extension settings."
Write-Host "  - Google Flow projects and files."
Write-Host "  - Windows Python, external environments, shared packages, and caches."
Write-Host "  - Git, uv, ngrok, and shared ngrok configuration."
Write-Host "  - ComfyUI, models, workflows, and ComfyUI-generated files."
Write-Host ""

if (-not $Confirm) {
    $Answer = Read-Host "Type UNINSTALL to continue"
    if ($Answer -cne "UNINSTALL") {
        Write-Host "Operation canceled. Nothing was removed."
        exit 0
    }
}

$Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$Principal = New-Object Security.Principal.WindowsPrincipal($Identity)
$IsAdministrator = $Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $IsAdministrator) {
    if ($Elevated) { throw "Administrator permission was not granted to complete the uninstall." }
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
        Write-Warning "The local configuration is invalid. The Flow Agent folder will be preserved."
    }
}

if (Test-Path -LiteralPath $StatePath -PathType Leaf) {
    try {
        $State = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
        if ($State.flow_pid) { Stop-ManagedProcessTree -RootProcessId ([int]$State.flow_pid) -ExpectedKind "flow" }
        if ($State.ngrok_pid) { Stop-ManagedProcessTree -RootProcessId ([int]$State.ngrok_pid) -ExpectedKind "ngrok" }
    } catch {
        Write-Warning "Not all registered processes could be stopped: $($_.Exception.Message)"
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
            Write-Host "Removed: $FlowRepoDir"
        }
        Remove-Item -LiteralPath $MarkerPath -Force -ErrorAction SilentlyContinue
        if ((Test-Path -LiteralPath $InstallRoot) -and -not (Get-ChildItem -LiteralPath $InstallRoot -Force | Select-Object -First 1)) {
            Remove-Item -LiteralPath $InstallRoot -Force
        }
        $RemovedManagedRepository = $true
    } else {
        Write-Warning "Ownership could not be verified. The Flow Agent folder was preserved."
    }
} else {
    Write-Warning "The installation has no valid ownership marker. The Flow Agent folder will be preserved."
}

if (Test-Path -LiteralPath $ShortcutPath -PathType Leaf) {
    try {
        $Shell = New-Object -ComObject WScript.Shell
        $Shortcut = $Shell.CreateShortcut($ShortcutPath)
        $ExpectedTarget = Get-FullPath (Join-Path $ScriptRoot "START-FLOW.cmd")
        if ((Get-FullPath $Shortcut.TargetPath) -eq $ExpectedTarget) {
            Remove-Item -LiteralPath $ShortcutPath -Force
        } else {
            Write-Warning "The shortcut was preserved because it points to another target."
        }
    } catch {
        Write-Warning "The shortcut could not be validated and was preserved."
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
Write-Host "UNINSTALL COMPLETE" -ForegroundColor Green
if (-not $RemovedManagedRepository) {
    Write-Host "The Flow Agent copy was preserved for safety because it had no verifiable installer marker." -ForegroundColor Yellow
}
Write-Host "Chrome and all personal user data remain untouched."
