$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot 'apps/ios')
foreach ($line in Get-Content -LiteralPath (Join-Path $PSScriptRoot '.local-data/main-review/main-api/mobile.env')) {
    if ($line -match '^([A-Z][A-Z0-9_]*)=(.*)$') {
        [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], 'Process')
    }
}
if ($env:CANOPY_TRIP_API_URL -ne 'https://func-canopy-dev-dxb0bgdgd6gghpd3.koreacentral-01.azurewebsites.net/api') {
    throw 'iOS release must use the main Azure API.'
}
$env:CANOPY_RELEASE_BUILD = 'true'
$env:CANOPY_LOCAL_ONLY = 'false'
$env:CANOPY_UI_PREVIEW = 'false'
$env:CANOPY_TRIP_ALLOW_LOCAL_HTTP = 'false'
if ([string]::IsNullOrWhiteSpace($env:EXPO_APPLE_ID)) { throw 'EXPO_APPLE_ID 환경변수에 본인의 Apple ID를 설정해 주세요.' }
Write-Host 'Canopy iOS build. Enter Apple credentials only at the EAS login prompts.'
& npx.cmd --yes eas-cli@latest build --platform ios --profile production
if ($LASTEXITCODE -ne 0) { throw 'EAS build did not complete. Send the error message, not your password.' }
