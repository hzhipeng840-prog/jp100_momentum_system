$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$requirements = Join-Path $root "requirements.txt"
$venv = Join-Path $root ".venv"
$venvPython = Join-Path $venv "Scripts\python.exe"
$candidates = @()
$pythonRoots = @()

if ($env:LOCALAPPDATA) {
    $pythonRoots += Join-Path $env:LOCALAPPDATA "Python"
}

$directory = Get-Item -LiteralPath $root
while ($directory) {
    $pythonRoots += Join-Path $directory.FullName "AppData\Local\Python"
    $directory = $directory.Parent
}

foreach ($pythonRoot in $pythonRoots | Select-Object -Unique) {
    if (Test-Path -LiteralPath $pythonRoot) {
        try {
            $pythonDirectories = Get-ChildItem -LiteralPath $pythonRoot -Directory -ErrorAction Stop
        }
        catch {
            continue
        }
        $candidates += $pythonDirectories |
            Sort-Object Name -Descending |
            ForEach-Object { Join-Path $_.FullName "python.exe" }
    }
}

$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if ($pythonCommand) {
    $candidates += $pythonCommand.Source
}

$python = $null
foreach ($candidate in $candidates | Select-Object -Unique) {
    if (-not (Test-Path -LiteralPath $candidate)) {
        continue
    }
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    & $candidate -c "import sys" *> $null
    $probeExitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousPreference
    if ($probeExitCode -eq 0) {
        $python = $candidate
        break
    }
}

if (-not $python) {
    throw "Python was not found."
}

$env:PYTHONIOENCODING = "utf-8"
$env:PIP_PROGRESS_BAR = "off"

if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "Creating the project virtual environment..."
    & $python -m venv $venv
    if ($LASTEXITCODE -ne 0) {
        throw "Virtual environment creation failed."
    }
}

Write-Host "Installing project dependencies..."
& $venvPython -m pip install -r $requirements
if ($LASTEXITCODE -ne 0) {
    throw "Dependency installation failed."
}

Write-Host "Setup completed."
Write-Host "Start the app with scripts/run_app.ps1"
