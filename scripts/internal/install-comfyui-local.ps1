param([string]$ComfyUIRoot = "")

$ErrorActionPreference = "Stop"
$Repository = "https://github.com/exjade/comfyui-flow-agent.git"

function Resolve-ComfyUIRoot([string]$RequestedRoot) {
    if (-not [string]::IsNullOrWhiteSpace($RequestedRoot)) {
        $Candidate = [IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($RequestedRoot)).TrimEnd('\')
        if (Test-Path -LiteralPath (Join-Path $Candidate "main.py") -PathType Leaf) { return $Candidate }
        throw "ComfyUI main.py was not found under: $Candidate"
    }

    $Candidates = @()
    $InstallationsPath = Join-Path $env:APPDATA "Comfy Desktop\installations.json"
    if (Test-Path -LiteralPath $InstallationsPath -PathType Leaf) {
        try {
            # Windows PowerShell 5 may preserve a top-level JSON array as one
            # pipeline object when it is wrapped directly in @(...). Assign it
            # first, then let foreach enumerate the actual array entries.
            $Installations = Get-Content -LiteralPath $InstallationsPath -Raw | ConvertFrom-Json
            foreach ($Installation in $Installations) {
                if ($Installation.status -ne "installed" -or -not $Installation.installPath) { continue }
                foreach ($Candidate in @(
                    (Join-Path ([string]$Installation.installPath) "ComfyUI"),
                    ([string]$Installation.installPath)
                )) {
                    if (Test-Path -LiteralPath (Join-Path $Candidate "main.py") -PathType Leaf) {
                        $Candidates += [IO.Path]::GetFullPath($Candidate).TrimEnd('\')
                    }
                }
            }
        } catch {
            Write-Warning "Comfy Desktop installations.json could not be read: $($_.Exception.Message)"
        }
    }

    $Candidates = @($Candidates | Select-Object -Unique)
    if ($Candidates.Count -eq 1) {
        $DetectedRoot = $Candidates[0]
        Write-Host "ComfyUI detectado / detected:" -ForegroundColor Cyan
        Write-Host "  $DetectedRoot"
        $RequestedPath = Read-Host "Presiona Enter para usarlo, o pega otra carpeta que contenga main.py"
        if ([string]::IsNullOrWhiteSpace($RequestedPath)) { return $DetectedRoot }
        return Resolve-ComfyUIRoot -RequestedRoot $RequestedPath
    }
    if ($Candidates.Count -gt 1) {
        Write-Host "Available local ComfyUI installations:" -ForegroundColor Cyan
        for ($Index = 0; $Index -lt $Candidates.Count; $Index++) {
            Write-Host "  $($Index + 1). $($Candidates[$Index])"
        }
        $SelectionText = Read-Host "Select the installation number"
        $Selection = 0
        if ([int]::TryParse($SelectionText, [ref]$Selection) -and $Selection -ge 1 -and $Selection -le $Candidates.Count) {
            return $Candidates[$Selection - 1]
        }
        throw "No valid ComfyUI installation was selected."
    }

    $ManualPath = Read-Host "ComfyUI Desktop was not detected. Paste the folder containing main.py"
    if ([string]::IsNullOrWhiteSpace($ManualPath)) { throw "A ComfyUI folder is required." }
    return Resolve-ComfyUIRoot -RequestedRoot $ManualPath
}

function Test-ComfyUIRunning([string]$Root) {
    $ResolvedRoot = [IO.Path]::GetFullPath($Root).TrimEnd('\')
    $ExpectedPython = [IO.Path]::GetFullPath((Join-Path $ResolvedRoot ".venv\Scripts\python.exe"))
    foreach ($Process in @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)) {
        $CommandLine = [string]$Process.CommandLine
        $ExecutablePath = [string]$Process.ExecutablePath
        $UsesThisRoot = (
            $CommandLine.IndexOf($ResolvedRoot, [StringComparison]::OrdinalIgnoreCase) -ge 0 -or
            $ExecutablePath.Equals($ExpectedPython, [StringComparison]::OrdinalIgnoreCase)
        )
        if ($CommandLine -match '(?i)main\.py' -and $UsesThisRoot) {
            return $true
        }
    }
    return $false
}

$ComfyUIRoot = Resolve-ComfyUIRoot -RequestedRoot $ComfyUIRoot
if (Test-ComfyUIRunning -Root $ComfyUIRoot) {
    throw "ComfyUI is still running. Fully close ComfyUI Desktop, then run this installer again."
}

$GitCommand = Get-Command git -ErrorAction SilentlyContinue
if (-not $GitCommand) { throw "Git was not found. Run 01-INSTALL-FLOW.cmd first." }
$CustomNodesDir = Join-Path $ComfyUIRoot "custom_nodes"
$NodeDir = Join-Path $CustomNodesDir "comfyui-flow-agent"
New-Item -ItemType Directory -Path $CustomNodesDir -Force | Out-Null

if (Test-Path -LiteralPath (Join-Path $NodeDir ".git") -PathType Container) {
    $Origin = (& $GitCommand.Source -C $NodeDir remote get-url origin).Trim()
    if ($LASTEXITCODE -ne 0 -or $Origin -notmatch '(?i)(github\.com[:/])exjade/comfyui-flow-agent(?:\.git)?$') {
        throw "The existing custom node has an unexpected Git origin and was preserved: $Origin"
    }
    & $GitCommand.Source -C $NodeDir diff --quiet
    $Dirty = $LASTEXITCODE -ne 0
    & $GitCommand.Source -C $NodeDir diff --cached --quiet
    $StagedDirty = $LASTEXITCODE -ne 0
    $Untracked = @(& $GitCommand.Source -C $NodeDir ls-files --others --exclude-standard)
    if ($Dirty -or $StagedDirty -or $Untracked.Count -gt 0) {
        $BackupLabel = "comfyui-flow-agent local installer backup $((Get-Date).ToUniversalTime().ToString('o'))"
        Write-Host "Local changes detected. Creating a recoverable Git stash before updating." -ForegroundColor Yellow
        & $GitCommand.Source -C $NodeDir stash push --include-untracked -m $BackupLabel
        if ($LASTEXITCODE -ne 0) { throw "The local custom node changes could not be backed up." }
    }
    & $GitCommand.Source -C $NodeDir pull --ff-only
    if ($LASTEXITCODE -ne 0) { throw "The local custom node could not be updated with a fast-forward pull." }
} elseif (Test-Path -LiteralPath $NodeDir) {
    throw "The custom node path exists but is not a Git repository. It was preserved: $NodeDir"
} else {
    & $GitCommand.Source clone $Repository $NodeDir
    if ($LASTEXITCODE -ne 0) { throw "The custom node could not be cloned from GitHub." }
}

$PythonCandidates = @(
    (Join-Path $ComfyUIRoot ".venv\Scripts\python.exe"),
    (Join-Path (Split-Path -Parent $ComfyUIRoot) ".venv\Scripts\python.exe"),
    (Join-Path $ComfyUIRoot "python_embeded\python.exe")
)
$ComfyPython = $PythonCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
if (-not $ComfyPython) {
    throw "The Python executable used by this ComfyUI installation was not found."
}

& $ComfyPython -m pip install -r (Join-Path $NodeDir "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "The custom node dependencies could not be installed." }

Write-Host ""
Write-Host "LOCAL CUSTOM NODE INSTALLATION COMPLETE" -ForegroundColor Green
Write-Host "ComfyUI: $ComfyUIRoot"
Write-Host "Custom node: $NodeDir"
Write-Host "Python: $ComfyPython"
Write-Host ""
Write-Host "Now run 04.1-START-FLOW-LOCAL.cmd, then open ComfyUI Desktop." -ForegroundColor Cyan
