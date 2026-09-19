$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (!(Test-Path .venv/Scripts/python.exe)) { python -m venv .venv }
& ./.venv/Scripts/python.exe -m pip install -r tools/local/requirements.txt
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& ./.venv/Scripts/python.exe tools/local/setup_population.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& ./.venv/Scripts/python.exe -m pip install 'torch==2.14.0+cpu' --index-url https://download.pytorch.org/whl/cpu
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Set-Location apps/ios
& npm.cmd ci --no-audit --no-fund
exit $LASTEXITCODE
