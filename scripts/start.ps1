$ErrorActionPreference = 'Stop'
$projectPath = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectPath '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run scripts/setup.ps1 first.' }
Set-Location -LiteralPath $projectPath
if (-not $env:TURINGTINT_COACH_PROFILE -and (Test-Path -LiteralPath '.cache/coaching-model-compact/manifest.json')) {
    $env:TURINGTINT_COACH_PROFILE = 'compact'
}
if (-not $env:OMP_NUM_THREADS) { $env:OMP_NUM_THREADS = '2' }
if (-not $env:MKL_NUM_THREADS) { $env:MKL_NUM_THREADS = '2' }
& $pythonPath -m turingtint
