param(
    [switch]$Check
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$candidates = @(
    (Join-Path $root ".venv\Scripts\python.exe")
)
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
    & $candidate -c "import streamlit" *> $null
    $probeExitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousPreference
    if ($probeExitCode -eq 0) {
        $python = $candidate
        break
    }
}

if (-not $python) {
    throw "Python with Streamlit was not found. Run scripts/setup.ps1 first."
}

$streamlitDir = Join-Path $env:USERPROFILE ".streamlit"
$credentialsPath = Join-Path $streamlitDir "credentials.toml"
if (-not (Test-Path -LiteralPath $credentialsPath)) {
    New-Item -ItemType Directory -Force -Path $streamlitDir | Out-Null
    @"
[general]
email = ""
"@ | Set-Content -LiteralPath $credentialsPath -Encoding ASCII
}

if ($Check) {
    Write-Host "Streamlit-ready Python was found."
    exit 0
}

Write-Host "Starting Streamlit with the project Python..."
& $python -m streamlit run (Join-Path $root "app.py") --browser.gatherUsageStats=false
exit $LASTEXITCODE
