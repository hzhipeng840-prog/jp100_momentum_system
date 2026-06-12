$ErrorActionPreference = "Stop"

Write-Host "Checking Python syntax..."
python -m compileall -q app.py daily_job.py src tests

Write-Host "Running offline unit tests..."
python -m unittest discover -s tests -v

Write-Host "Checking diff whitespace..."
git diff --check

Write-Host "Verification completed."
