$ErrorActionPreference = 'Stop'
$tripRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$tripPython = Join-Path $tripRoot 'apps/api/.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $tripPython)) { throw 'apps/api/README.md의 최초 설치 명령을 먼저 실행하세요.' }
Push-Location (Join-Path $tripRoot 'apps/api')
try {
  & $tripPython -m unittest discover -s tests -v
  if ($LASTEXITCODE -ne 0) { throw 'Trip API tests failed' }
} finally { Pop-Location }
Push-Location (Join-Path $tripRoot 'apps/ios')
try {
  $env:CANOPY_TEST_PYTHON = $tripPython
  npm test
  if ($LASTEXITCODE -ne 0) { throw 'Trip mobile integration tests failed' }
  npm run typecheck
  if ($LASTEXITCODE -ne 0) { throw 'TypeScript check failed' }
} finally { Pop-Location }
& $tripPython (Join-Path $tripRoot 'tools/azure/package_trip_api.py')
if ($LASTEXITCODE -ne 0) { throw 'Functions packaging failed' }
Write-Output '로컬 검증 완료. Azure 배포 및 실제 iPhone 검증은 수행하지 않았습니다.'
