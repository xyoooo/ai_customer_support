$ErrorActionPreference = "Stop"

& "$PSScriptRoot\..\.venv\Scripts\ruff.exe" check .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& "$PSScriptRoot\..\.venv\Scripts\ruff.exe" format --check .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& "$PSScriptRoot\..\.venv\Scripts\mypy.exe" apps packages
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& "$PSScriptRoot\..\.venv\Scripts\pytest.exe" --cov=apps --cov=packages --cov-report=term
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Push-Location "$PSScriptRoot\..\apps\web"
try {
    & npm.cmd run check
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & npm.cmd run check:api
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}
