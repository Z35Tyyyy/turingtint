$ErrorActionPreference = 'Stop'
$projectPath = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectPath
$pythonPath = Join-Path $projectPath '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    & python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment setup failed.' }
}
& $pythonPath -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
Write-Output 'Setup complete. Seed references with: .venv/Scripts/python.exe -m corpus_tools fetch --limit 12'
Write-Output 'Start with: powershell -ExecutionPolicy Bypass -File scripts/start.ps1'
