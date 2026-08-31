param(
    [string]$InstallRoot = "$env:USERPROFILE\FlowAgent",
    [int]$Port = 8001
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$LauncherRoot = Split-Path -Parent $ScriptRoot
$RepositoryRoot = Split-Path -Parent $LauncherRoot
$BackendPatchPath = Join-Path $RepositoryRoot "patches\flow-agent-media-reuse.patch"
$BackendVideoPatchPath = Join-Path $RepositoryRoot "patches\flow-agent-video-reference.patch"
$BackendPatches = @(
    @{ Path = $BackendPatchPath; Name = "media reuse fix" },
    @{ Path = $BackendVideoPatchPath; Name = "conditioned-video fix" }
)
$DataRoot = Join-Path $env:LOCALAPPDATA "ComfyUIFlowAgent"
$ConfigPath = Join-Path $DataRoot "flow-local.config.json"
$FlowRepository = "https://github.com/kodelyx/flow-agent.git"
$FlowRepoDir = Join-Path $InstallRoot "flow-agent"
$FlowAgentDir = Join-Path $FlowRepoDir "flow-agent"
$ExtensionDir = Join-Path $FlowRepoDir "flow-extension"
$EnvPath = Join-Path $FlowAgentDir ".env"
$InstallMarkerPath = Join-Path $InstallRoot ".comfyui-flow-agent-install.json"
$CreatedFlowRepository = $false

function Write-Step([string]$Text) {
    Write-Host ""
    Write-Host $Text -ForegroundColor Cyan
}

function Refresh-Path {
    $MachinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$MachinePath;$UserPath"
}

function Find-CommandPath([string]$Name) {
    $Command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($Command) { return $Command.Source }
    return $null
}

function Test-BackendPatchApplied([string]$GitExe, [string]$PatchPath) {
    if (-not (Test-Path -LiteralPath $PatchPath -PathType Leaf)) { return $false }
    & $GitExe -C $FlowAgentDir apply --reverse --check --unidiff-zero $PatchPath 2>$null
    return $LASTEXITCODE -eq 0
}

function Apply-BackendPatchFile([string]$GitExe, [string]$PatchPath, [string]$PatchName) {
    if (-not (Test-Path -LiteralPath $PatchPath -PathType Leaf)) {
        throw "Required Flow Agent compatibility patch is missing: $PatchPath"
    }
    if (Test-BackendPatchApplied $GitExe $PatchPath) {
        Write-Host "Flow Agent $PatchName is already installed." -ForegroundColor Green
        return
    }
    & $GitExe -C $FlowAgentDir apply --check --unidiff-zero $PatchPath
    if ($LASTEXITCODE -ne 0) {
        throw "The installed Flow Agent version is not compatible with the $PatchName. Update comfyui-flow-agent and retry."
    }
    & $GitExe -C $FlowAgentDir apply --unidiff-zero $PatchPath
    if ($LASTEXITCODE -ne 0) { throw "The Flow Agent $PatchName could not be installed." }
    Write-Host "Installed Flow Agent $PatchName." -ForegroundColor Green
}

function Apply-BackendPatches([string]$GitExe) {
    foreach ($Patch in $BackendPatches) {
        Apply-BackendPatchFile $GitExe $Patch.Path $Patch.Name
    }
}

function Install-WingetPackage(
    [string]$DisplayName,
    [string[]]$WingetArguments,
    [string]$CommandName
) {
    $Existing = Find-CommandPath $CommandName
    if ($Existing) {
        Write-Host "$DisplayName is already installed: $Existing" -ForegroundColor Green
        return $Existing
    }
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "Windows Package Manager (winget) is unavailable. Update App Installer from Microsoft Store."
    }

    Write-Host "Installing $DisplayName..." -ForegroundColor Yellow
    & winget @WingetArguments --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "winget could not install $DisplayName (exit code $LASTEXITCODE)."
    }
    Refresh-Path
    $Installed = Find-CommandPath $CommandName
    if (-not $Installed) {
        throw "$DisplayName was installed, but '$CommandName' is not available yet. Restart Windows and run 01-INSTALL-FLOW.cmd again."
    }
    return $Installed
}

function Convert-SecureStringToText([Security.SecureString]$Value) {
    $Pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($Pointer)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Pointer)
    }
}

function New-ApiKey {
    $Bytes = New-Object byte[] 32
    $Generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $Generator.GetBytes($Bytes) } finally { $Generator.Dispose() }
    return [Convert]::ToBase64String($Bytes).TrimEnd("=").Replace("+", "-").Replace("/", "_")
}

function Get-DotEnvValue([string]$Name) {
    if (-not (Test-Path -LiteralPath $EnvPath -PathType Leaf)) { return "" }
    $Line = Get-Content -LiteralPath $EnvPath |
        Where-Object { $_ -match "^$([regex]::Escape($Name))=" } |
        Select-Object -Last 1
    if (-not $Line) { return "" }
    return $Line.Split("=", 2)[1].Trim().Trim('"').Trim("'")
}

function Set-DotEnvValue([string]$Name, [string]$Value) {
    $Lines = if (Test-Path -LiteralPath $EnvPath) {
        @(Get-Content -LiteralPath $EnvPath)
    } else {
        @("# Flow Agent user settings")
    }
    $Replacement = "$Name=$Value"
    $Found = $false
    $Updated = foreach ($Line in $Lines) {
        if ($Line -match "^$([regex]::Escape($Name))=") {
            $Found = $true
            $Replacement
        } else {
            $Line
        }
    }
    if (-not $Found) { $Updated += $Replacement }
    $Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllLines($EnvPath, [string[]]$Updated, $Utf8NoBom)
}

function Get-ProjectId([string]$InputValue) {
    $Candidate = $InputValue.Trim().TrimEnd("/")
    if ($Candidate -match "/project/([0-9a-fA-F-]{20,})") { return $Matches[1] }
    if ($Candidate -match "^[0-9a-fA-F-]{20,}$") { return $Candidate }
    return $null
}

function Find-ChromiumBrowser {
    $Candidates = @(
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
        "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe",
        "$env:ProgramFiles\BraveSoftware\Brave-Browser\Application\brave.exe",
        "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
    )
    return $Candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
        Select-Object -First 1
}

Write-Host "FLOW AGENT + NGROK INITIAL SETUP" -ForegroundColor Magenta
Write-Host "Local installation: $InstallRoot"

Write-Step "1/7 Installing required tools"
$GitExe = Install-WingetPackage "Git" @(
    "install", "--id", "Git.Git", "-e"
) "git.exe"
$UvExe = Install-WingetPackage "uv" @(
    "install", "--id", "astral-sh.uv", "-e"
) "uv.exe"
$NgrokExe = Install-WingetPackage "ngrok" @(
    "install", "ngrok", "-s", "msstore"
) "ngrok.exe"
$BrowserExe = Find-ChromiumBrowser
if (-not $BrowserExe) {
    Write-Host "Installing Google Chrome..." -ForegroundColor Yellow
    & winget install --id Google.Chrome -e --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { throw "winget could not install Google Chrome." }
    Refresh-Path
    $BrowserExe = Find-ChromiumBrowser
    if (-not $BrowserExe) {
        throw "Google Chrome was installed, but is not available yet. Restart Windows and run 01-INSTALL-FLOW.cmd again."
    }
}

Write-Step "2/7 Downloading Flow Agent"
New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null
if (Test-Path -LiteralPath (Join-Path $FlowRepoDir ".git")) {
    $AppliedBackendPatches = @(
        $BackendPatches | Where-Object { Test-BackendPatchApplied $GitExe $_.Path }
    )
    for ($Index = $AppliedBackendPatches.Count - 1; $Index -ge 0; $Index--) {
        $Patch = $AppliedBackendPatches[$Index]
        & $GitExe -C $FlowAgentDir apply --reverse --unidiff-zero $Patch.Path
        if ($LASTEXITCODE -ne 0) { throw "The existing Flow Agent $($Patch.Name) could not be prepared for update." }
    }
    & $GitExe -C $FlowRepoDir pull --ff-only
    if ($LASTEXITCODE -ne 0) {
        foreach ($Patch in $AppliedBackendPatches) {
            Apply-BackendPatchFile $GitExe $Patch.Path $Patch.Name
        }
        throw "Flow Agent could not be updated."
    }
} elseif (Test-Path -LiteralPath $FlowRepoDir) {
    throw "'$FlowRepoDir' exists but is not a Git repository. Move it or choose another InstallRoot."
} else {
    & $GitExe clone $FlowRepository $FlowRepoDir
    if ($LASTEXITCODE -ne 0) { throw "Flow Agent could not be cloned." }
    $CreatedFlowRepository = $true
}
Apply-BackendPatches $GitExe

Write-Step "3/7 Preparing the isolated runtime and dependencies"
Push-Location $FlowAgentDir
try {
    & $UvExe sync
    if ($LASTEXITCODE -ne 0) { throw "uv sync could not prepare Flow Agent." }
} finally {
    Pop-Location
}

Write-Step "4/7 Configuring ngrok"
Start-Process "https://dashboard.ngrok.com/get-started/your-authtoken"
$SecureToken = Read-Host "Paste your ngrok authtoken (input is hidden)" -AsSecureString
$NgrokToken = Convert-SecureStringToText $SecureToken
if ([string]::IsNullOrWhiteSpace($NgrokToken)) { throw "The ngrok authtoken is empty." }
& $NgrokExe config add-authtoken $NgrokToken
$NgrokToken = $null
if ($LASTEXITCODE -ne 0) { throw "ngrok rejected the authtoken." }

Write-Step "5/7 Installing the browser extension"
$ExtensionDir | Set-Clipboard
Start-Process explorer.exe -ArgumentList @("/select,`"$ExtensionDir\manifest.json`"")
if ($BrowserExe) {
    Start-Process -FilePath $BrowserExe -ArgumentList "chrome://extensions"
} else {
    Start-Process "https://support.google.com/chrome_webstore/answer/2664769"
}
Write-Host "On the extensions page:" -ForegroundColor Yellow
Write-Host "  1. Enable Developer mode."
Write-Host "  2. Click Load unpacked."
Write-Host "  3. Select the folder copied to the clipboard: $ExtensionDir"
Read-Host "Press Enter after the Flow Agent extension is installed"

Write-Step "6/7 Selecting a Google Flow project"
$FlowHome = "https://labs.google/fx/es-419/tools/flow"
if ($BrowserExe) {
    Start-Process -FilePath $BrowserExe -ArgumentList $FlowHome
} else {
    Start-Process $FlowHome
}
Write-Host "Sign in, create or open a project, and copy its full URL." -ForegroundColor Yellow
$ProjectId = $null
while (-not $ProjectId) {
    $ProjectInput = Read-Host "Paste the Google Flow project URL"
    $ProjectId = Get-ProjectId $ProjectInput
    if (-not $ProjectId) { Write-Host "The project ID was not recognized. Try again." -ForegroundColor Red }
}

Write-Step "7/7 Creating secure configuration"
New-Item -ItemType Directory -Path $DataRoot -Force | Out-Null
$ExistingApiKey = Get-DotEnvValue "SERVER_API_KEY"
$ApiKey = if ([string]::IsNullOrWhiteSpace($ExistingApiKey)) {
    New-ApiKey
} else {
    $ExistingApiKey
}
$Settings = [ordered]@{
    IMAGE_MODEL = "gem_pix_2"
    OPENAI_API_HOST = "127.0.0.1"
    OPENAI_API_PORT = "$Port"
    SERVER_API_KEY = $ApiKey
    PUBLIC_BASE_URL = "http://127.0.0.1:$Port"
    DEFAULT_PROJECT = $ProjectId
    MAX_CONCURRENT_REQUESTS = "5"
    REQUEST_MIN_INTERVAL = "3"
    MEDIA_ID_VALIDATION_TTL_SECONDS = "21600"
}
foreach ($Setting in $Settings.GetEnumerator()) {
    Set-DotEnvValue $Setting.Key $Setting.Value
}

$ExistingMarker = $null
if (Test-Path -LiteralPath $InstallMarkerPath -PathType Leaf) {
    try {
        $ExistingMarker = Get-Content -LiteralPath $InstallMarkerPath -Raw | ConvertFrom-Json
    } catch {
        Write-Warning "The existing installation marker is invalid. The folder will not be claimed as managed."
    }
}
$ManagedFlowRepository = $CreatedFlowRepository -or (
    $ExistingMarker -and
    $ExistingMarker.install_id -and
    ([string]$ExistingMarker.flow_repo_dir -eq $FlowRepoDir)
)
$InstallId = if ($ManagedFlowRepository -and $ExistingMarker.install_id) {
    [string]$ExistingMarker.install_id
} elseif ($CreatedFlowRepository) {
    [guid]::NewGuid().ToString("D")
} else {
    ""
}
if ($CreatedFlowRepository) {
    $Marker = [ordered]@{
        install_id = $InstallId
        flow_repo_dir = $FlowRepoDir
        created_at = (Get-Date).ToString("o")
        created_by = "comfyui-flow-agent"
    }
    $Marker | ConvertTo-Json | Set-Content -LiteralPath $InstallMarkerPath -Encoding utf8
}

$Config = [ordered]@{
    flow_agent_dir = $FlowAgentDir
    ngrok_exe = $NgrokExe
    port = $Port
    install_root = $InstallRoot
    flow_repo_dir = $FlowRepoDir
    install_marker = $InstallMarkerPath
    install_id = $InstallId
    managed_flow_repository = [bool]$ManagedFlowRepository
}
$Config | ConvertTo-Json | Set-Content -LiteralPath $ConfigPath -Encoding utf8

$Desktop = [Environment]::GetFolderPath("Desktop")
$WshShell = New-Object -ComObject WScript.Shell
$LegacyShortcutPath = Join-Path $Desktop "START FLOW AGENT.lnk"
if (Test-Path -LiteralPath $LegacyShortcutPath -PathType Leaf) {
    try {
        $LegacyShortcut = $WshShell.CreateShortcut($LegacyShortcutPath)
        $LegacyTarget = [IO.Path]::GetFullPath((Join-Path $LauncherRoot "04-START-FLOW.cmd"))
        if ([IO.Path]::GetFullPath($LegacyShortcut.TargetPath) -eq $LegacyTarget) {
            Remove-Item -LiteralPath $LegacyShortcutPath -Force
        }
    } catch {
        Write-Warning "The old desktop shortcut could not be validated and was preserved."
    }
}
$ShortcutDefinitions = @(
    @{ Name = "START FLOW AGENT - RUNPOD.lnk"; Launcher = "04-START-FLOW-RUNPOD.cmd" },
    @{ Name = "START FLOW AGENT - LOCAL.lnk"; Launcher = "04.1-START-FLOW-LOCAL.cmd" }
)
foreach ($Definition in $ShortcutDefinitions) {
    $ShortcutPath = Join-Path $Desktop $Definition.Name
    $Shortcut = $WshShell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = Join-Path $LauncherRoot $Definition.Launcher
    $Shortcut.WorkingDirectory = $LauncherRoot
    $Shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,137"
    $Shortcut.Save()
}

Write-Host ""
Write-Host "LOCAL INSTALLATION COMPLETE" -ForegroundColor Green
Write-Host "Continue with the numbered launchers in the scripts folder:"
Write-Host "  2. 02-COPY-API-KEY.cmd"
Write-Host "  3. 03-SHOW-RUNPOD-INSTALL.cmd"
Write-Host "  3.1 03.1-INSTALL-OR-UPDATE-CUSTOM-NODE-LOCAL.cmd (local ComfyUI only)"
Write-Host "  4. 04-START-FLOW-RUNPOD.cmd (when ComfyUI runs on RunPod)"
Write-Host "  4.1 04.1-START-FLOW-LOCAL.cmd (when ComfyUI runs on this PC)"
