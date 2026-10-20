$ErrorActionPreference = 'Stop'
$projectPath = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectPath
$pythonPath = Join-Path $projectPath '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    & python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment setup failed.' }
}
if (Get-Command uv -ErrorAction SilentlyContinue) {
    & uv pip install --python $pythonPath -r requirements-hybrid.txt
} else {
    & $pythonPath -m ensurepip
    & $pythonPath -m pip install -r requirements-hybrid.txt
}
if ($LASTEXITCODE -ne 0) { throw 'Hybrid dependency installation failed.' }
& $pythonPath -m detector_models.hybrid download
if ($LASTEXITCODE -ne 0) { throw 'Pinned model acquisition failed.' }
Write-Output 'Hybrid ready. Start scripts/start.ps1 and use Check text.'
