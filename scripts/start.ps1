param([int]$Port = 8000)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$pythonExe = Join-Path (Get-Location) ".venv/Scripts/python.exe"
if (-not (Test-Path $pythonExe)) { throw "Create .venv and install requirements.txt first; see README.md." }
if (-not (Test-Path "frontend/dist/index.html")) { throw "Build frontend first: npm --prefix frontend ci; npm --prefix frontend run build" }
& $pythonExe -m uvicorn backend.app.main:app --no-access-log --host 127.0.0.1 --port $Port
exit $LASTEXITCODE
