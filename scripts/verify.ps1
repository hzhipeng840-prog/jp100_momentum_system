$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$safeRoot = $root.Replace("\", "/")

Push-Location $root
try {
    Write-Host "Checking Python syntax..."
    & python -m compileall -q app.py daily_job.py cloud_job.py src tests scripts/export_cloud_data.py
    if ($LASTEXITCODE -ne 0) {
        throw "Python syntax check failed."
    }

    Write-Host "Running offline unit tests..."
    & python -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) {
        throw "Offline unit tests failed."
    }

    Write-Host "Checking diff whitespace..."
    & git -c "safe.directory=$safeRoot" -C $safeRoot diff --check
    if ($LASTEXITCODE -ne 0) {
        throw "Git diff whitespace check failed."
    }

    Write-Host "Verification completed."
}
finally {
    Pop-Location
}
