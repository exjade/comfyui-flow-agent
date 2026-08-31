param(
    [switch]$Elevated,
    [switch]$Confirm
)

$ErrorActionPreference = "Stop"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$LauncherRoot = Split-Path -Parent $ScriptRoot
$DataRoot = Join-Path $env:LOCALAPPDATA "ComfyUIFlowAgent"
$ConfigPath = Join-Path $DataRoot "flow-local.config.json"
$StatePath = Join-Path $DataRoot "flow-local-state.json"
$LegacyConfigPath = Join-Path $LauncherRoot "flow-local.config.json"
$LegacyStatePath = Join-Path $LauncherRoot ".flow-local-state.json"
if (-not (Test-Path -LiteralPath $ConfigPath) -and (Test-Path -LiteralPath $LegacyConfigPath)) { $ConfigPath = $LegacyConfigPath }
if (-not (Test-Path -LiteralPath $StatePath) -and (Test-Path -LiteralPath $LegacyStatePath)) { $StatePath = $LegacyStatePath }
$Desktop = [Environment]::GetFolderPath("Desktop")
$ShortcutDefinitions = @(
    @{ Path = Join-Path $Desktop "START FLOW AGENT - RUNPOD.lnk"; Launcher = "04-START-FLOW-RUNPOD.cmd" },
    @{ Path = Join-Path $Desktop "START FLOW AGENT - LOCAL.lnk"; Launcher = "04.1-START-FLOW-LOCAL.cmd" },
    @{ Path = Join-Path $Desktop "START FLOW AGENT.lnk"; Launcher = "04-START-FLOW.cmd" }
)

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

# Remove only the Windows variables that this installation can prove it owns.
if ($Config -and $Config.flow_agent_dir) {
    $ConfiguredPort = if ($Config.port) { [int]$Config.port } else { 8001 }
    $ExpectedLocalUrl = "http://127.0.0.1:$ConfiguredPort"
    $InstalledApiKey = ""
    $InstalledEnvPath = Join-Path ([string]$Config.flow_agent_dir) ".env"
    if (Test-Path -LiteralPath $InstalledEnvPath -PathType Leaf) {
        $ApiKeyLine = Get-Content -LiteralPath $InstalledEnvPath |
            Where-Object { $_ -match '^SERVER_API_KEY=' } | Select-Object -Last 1
        if ($ApiKeyLine) { $InstalledApiKey = $ApiKeyLine.Split('=', 2)[1].Trim().Trim('"').Trim("'") }
    }
    if ([Environment]::GetEnvironmentVariable("FLOW_AGENT_BASE_URL", "User") -eq $ExpectedLocalUrl) {
        [Environment]::SetEnvironmentVariable("FLOW_AGENT_BASE_URL", $null, "User")
    }
    if ($InstalledApiKey -and [Environment]::GetEnvironmentVariable("FLOW_AGENT_API_KEY", "User") -eq $InstalledApiKey) {
        [Environment]::SetEnvironmentVariable("FLOW_AGENT_API_KEY", $null, "User")
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

foreach ($Definition in $ShortcutDefinitions) {
    if (Test-Path -LiteralPath $Definition.Path -PathType Leaf) {
        try {
            $Shell = New-Object -ComObject WScript.Shell
            $Shortcut = $Shell.CreateShortcut($Definition.Path)
            $ExpectedTarget = Get-FullPath (Join-Path $LauncherRoot $Definition.Launcher)
            if ((Get-FullPath $Shortcut.TargetPath) -eq $ExpectedTarget) {
                Remove-Item -LiteralPath $Definition.Path -Force
            } else {
                Write-Warning "The shortcut '$($Definition.Path)' was preserved because it points to another target."
            }
        } catch {
            Write-Warning "The shortcut '$($Definition.Path)' could not be validated and was preserved."
        }
    }
}

$LocalArtifacts = @(
    $StatePath,
    $ConfigPath,
    (Join-Path $DataRoot "flow-agent.stdout.log"),
    (Join-Path $DataRoot "flow-agent.stderr.log"),
    (Join-Path $DataRoot "ngrok.log"),
    $LegacyConfigPath,
    $LegacyStatePath,
    (Join-Path $LauncherRoot "flow-agent.stdout.log"),
    (Join-Path $LauncherRoot "flow-agent.stderr.log"),
    (Join-Path $LauncherRoot "ngrok.log")
)
foreach ($Artifact in $LocalArtifacts) {
    Remove-Item -LiteralPath $Artifact -Force -ErrorAction SilentlyContinue
}
if ((Test-Path -LiteralPath $DataRoot) -and -not (Get-ChildItem -LiteralPath $DataRoot -Force | Select-Object -First 1)) {
    Remove-Item -LiteralPath $DataRoot -Force
}

Write-Host ""
Write-Host "UNINSTALL COMPLETE" -ForegroundColor Green
if (-not $RemovedManagedRepository) {
    Write-Host "The Flow Agent copy was preserved for safety because it had no verifiable installer marker." -ForegroundColor Yellow
}
Write-Host "Chrome and all personal user data remain untouched."
