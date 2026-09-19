param([switch]$Weekly)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
$env:CANOPY_TEST_PYTHON = $python
if (Test-Path '.local-data/runtime/java/bin/java.exe') { $env:JAVA_HOME = Join-Path $PSScriptRoot '.local-data/runtime/java' }
& $python -m pytest tools/local/test_local.py tools/local/test_business.py tools/local/test_rewards.py -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Push-Location apps/ios
try {
    & npm.cmd run typecheck
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & npm.cmd test
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally { Pop-Location }
if ($Weekly) {
    & $python tools/local/weekly.py --inputs .local-data/end-to-end/inputs --output .local-data/end-to-end/weekly
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $python tools/local/seed_scenario.py
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $python tools/local/weekly.py --inputs .local-data/scenarios/baseline/inputs --output .local-data/scenarios/baseline/weekly --commute-verified
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
