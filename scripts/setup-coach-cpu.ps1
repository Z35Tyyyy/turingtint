$ErrorActionPreference = 'Stop'
$projectPath = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectPath
$pythonPath = Join-Path $projectPath '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run scripts/setup-hybrid.ps1 first.' }
if (Get-Command uv -ErrorAction SilentlyContinue) {
    & uv pip install --python $pythonPath -r requirements-coach.txt
} else {
    & $pythonPath -m ensurepip
    & $pythonPath -m pip install -r requirements-coach.txt
}
if ($LASTEXITCODE -ne 0) { throw 'Coach dependency installation failed.' }
& $pythonPath scripts/setup_coach.py --profile compact
if ($LASTEXITCODE -ne 0) { throw 'Compact coach acquisition failed.' }
Write-Output 'Local CPU coach installed. Restart with scripts/start.ps1.'
