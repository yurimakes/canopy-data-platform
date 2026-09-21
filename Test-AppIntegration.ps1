$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $python = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
    $env:CANOPY_TEST_PYTHON = $python
    $env:PYTHONPATH = 'apps/api;tools/local;cloud/azure/functions/func_canopy_dev;.'
    & $python -m pytest apps/api/tests tests/test_function_package.py tools/local/test_hosted_domain.py tools/local/test_trip_settlement.py -q
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Push-Location apps/ios
    try {
        & npm.cmd run typecheck
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & npm.cmd test
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } finally { Pop-Location }
} finally { Pop-Location }
