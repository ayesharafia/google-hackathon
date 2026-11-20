# Reuse the existing environment and private local data; no dependency installation.
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$pythonPath = Join-Path $repoRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Create the Python 3.11 .venv and install the project dependencies first.'
}
$dataPath = Join-Path $repoRoot '.backend/local-hackathon'
New-Item -ItemType Directory -Force $dataPath | Out-Null
$tokenPath = Join-Path $dataPath 'dev-token.txt'
if (-not (Test-Path -LiteralPath $tokenPath)) {
    & $pythonPath -c 'import pathlib,secrets,sys; pathlib.Path(sys.argv[1]).write_text(secrets.token_urlsafe(32))' $tokenPath
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the development token.' }
}
$env:PHYSIMESH_DATA_ROOT = $dataPath
$env:PHYSIMESH_DB_PATH = Join-Path $dataPath 'jobs.sqlite'
$env:PHYSIMESH_API_TOKEN = Get-Content -LiteralPath $tokenPath -Raw
$env:PHYSIMESH_PUBLIC_ACCESS = '0'
$env:PHYSIMESH_MODE = 'local'
$env:PHYSIMESH_BIND_HOST = '127.0.0.1'
Push-Location $repoRoot
try {
    & $pythonPath -m uvicorn physimesh.api.app:app_from_environment --factory --host 127.0.0.1 --port 8768
} finally {
    Pop-Location
}
