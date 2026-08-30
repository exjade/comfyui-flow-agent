param(
    [string]$InstallRoot = "$env:USERPROFILE\FlowAgent",
    [int]$Port = 8001
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ConfigPath = Join-Path $ScriptRoot "flow-local.config.json"
$FlowRepository = "https://github.com/kodelyx/flow-agent.git"
$FlowRepoDir = Join-Path $InstallRoot "flow-agent"
$FlowAgentDir = Join-Path $FlowRepoDir "flow-agent"
$ExtensionDir = Join-Path $FlowRepoDir "flow-extension"
$EnvPath = Join-Path $FlowAgentDir ".env"

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

function Install-WingetPackage(
    [string]$DisplayName,
    [string[]]$WingetArguments,
    [string]$CommandName
) {
    $Existing = Find-CommandPath $CommandName
    if ($Existing) {
        Write-Host "$DisplayName ya esta instalado: $Existing" -ForegroundColor Green
        return $Existing
    }
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "Windows Package Manager (winget) no esta disponible. Actualiza App Installer desde Microsoft Store."
    }

    Write-Host "Instalando $DisplayName..." -ForegroundColor Yellow
    & winget @WingetArguments --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "winget no pudo instalar $DisplayName (codigo $LASTEXITCODE)."
    }
    Refresh-Path
    $Installed = Find-CommandPath $CommandName
    if (-not $Installed) {
        throw "$DisplayName se instalo, pero '$CommandName' aun no esta disponible. Reinicia Windows y vuelve a ejecutar INSTALAR-FLOW.cmd."
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

Write-Host "INSTALADOR INICIAL - FLOW AGENT + NGROK" -ForegroundColor Magenta
Write-Host "Instalacion local: $InstallRoot"

Write-Step "1/7 Instalando herramientas"
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
    Write-Host "Instalando Google Chrome..." -ForegroundColor Yellow
    & winget install --id Google.Chrome -e --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { throw "winget no pudo instalar Google Chrome." }
    Refresh-Path
    $BrowserExe = Find-ChromiumBrowser
    if (-not $BrowserExe) {
        throw "Google Chrome se instalo, pero aun no esta disponible. Reinicia Windows y vuelve a ejecutar INSTALAR-FLOW.cmd."
    }
}

Write-Step "2/7 Descargando Flow Agent"
New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null
if (Test-Path -LiteralPath (Join-Path $FlowRepoDir ".git")) {
    & $GitExe -C $FlowRepoDir pull --ff-only
    if ($LASTEXITCODE -ne 0) { throw "No se pudo actualizar Flow Agent." }
} elseif (Test-Path -LiteralPath $FlowRepoDir) {
    throw "La carpeta '$FlowRepoDir' existe, pero no es un repositorio Git. Muevela o elige otro InstallRoot."
} else {
    & $GitExe clone $FlowRepository $FlowRepoDir
    if ($LASTEXITCODE -ne 0) { throw "No se pudo clonar Flow Agent." }
}

Write-Step "3/7 Preparando Python y dependencias"
Push-Location $FlowAgentDir
try {
    & $UvExe sync
    if ($LASTEXITCODE -ne 0) { throw "uv sync no pudo preparar Flow Agent." }
} finally {
    Pop-Location
}

Write-Step "4/7 Configurando ngrok"
Start-Process "https://dashboard.ngrok.com/get-started/your-authtoken"
$SecureToken = Read-Host "Pega tu authtoken de ngrok (se ocultara)" -AsSecureString
$NgrokToken = Convert-SecureStringToText $SecureToken
if ([string]::IsNullOrWhiteSpace($NgrokToken)) { throw "El authtoken de ngrok esta vacio." }
& $NgrokExe config add-authtoken $NgrokToken
$NgrokToken = $null
if ($LASTEXITCODE -ne 0) { throw "ngrok rechazo el authtoken." }

Write-Step "5/7 Instalando la extension del navegador"
$ExtensionDir | Set-Clipboard
Start-Process explorer.exe -ArgumentList @("/select,`"$ExtensionDir\manifest.json`"")
if ($BrowserExe) {
    Start-Process -FilePath $BrowserExe -ArgumentList "chrome://extensions"
} else {
    Start-Process "https://support.google.com/chrome_webstore/answer/2664769"
}
Write-Host "En la pagina de extensiones:" -ForegroundColor Yellow
Write-Host "  1. Activa Modo de desarrollador."
Write-Host "  2. Pulsa Cargar descomprimida."
Write-Host "  3. Selecciona la carpeta copiada al portapapeles: $ExtensionDir"
Read-Host "Pulsa Enter cuando la extension Flow Agent este instalada"

Write-Step "6/7 Seleccionando un proyecto de Google Flow"
$FlowHome = "https://labs.google/fx/es-419/tools/flow"
if ($BrowserExe) {
    Start-Process -FilePath $BrowserExe -ArgumentList $FlowHome
} else {
    Start-Process $FlowHome
}
Write-Host "Inicia sesion, crea o abre un proyecto y copia su URL completa." -ForegroundColor Yellow
$ProjectId = $null
while (-not $ProjectId) {
    $ProjectInput = Read-Host "Pega la URL del proyecto de Google Flow"
    $ProjectId = Get-ProjectId $ProjectInput
    if (-not $ProjectId) { Write-Host "No pude reconocer el ID del proyecto. Intentalo otra vez." -ForegroundColor Red }
}

Write-Step "7/7 Creando configuracion segura"
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
}
foreach ($Setting in $Settings.GetEnumerator()) {
    Set-DotEnvValue $Setting.Key $Setting.Value
}

$Config = [ordered]@{
    flow_agent_dir = $FlowAgentDir
    ngrok_exe = $NgrokExe
    port = $Port
}
$Config | ConvertTo-Json | Set-Content -LiteralPath $ConfigPath -Encoding utf8

$Desktop = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $Desktop "INICIAR FLOW AGENT.lnk"
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = Join-Path $ScriptRoot "INICIAR-FLOW.cmd"
$Shortcut.WorkingDirectory = $ScriptRoot
$Shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,137"
$Shortcut.Save()

$ApiKey | Set-Clipboard
Write-Host ""
Write-Host "CLAVE COPIADA AL PORTAPAPELES" -ForegroundColor Green
Write-Host "En RunPod crea el secreto 'flow_agent_api_key' y pega ahora la clave."
Write-Host "Despues asigna: FLOW_AGENT_API_KEY={{ RUNPOD_SECRET_flow_agent_api_key }}"
Read-Host "Pulsa Enter solamente despues de guardar el secreto en RunPod"

& (Join-Path $ScriptRoot "start-flow-local.ps1")
Write-Host ""
Write-Host "INSTALACION TERMINADA" -ForegroundColor Green
Write-Host "La URL publica quedo copiada. Guardala como FLOW_AGENT_BASE_URL en RunPod."
