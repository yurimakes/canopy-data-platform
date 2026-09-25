$ErrorActionPreference = 'Stop'
$env:CANOPY_UI_PREVIEW = 'true'
Set-Location (Join-Path $PSScriptRoot 'apps/ios')
Write-Host 'Preview: http://localhost:8097/?design-preview=1'
& npx.cmd expo start --web --localhost --port 8097
