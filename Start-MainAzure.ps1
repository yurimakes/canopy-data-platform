param([int]$Port = 8082)
$ErrorActionPreference = 'Stop'
$configPath = Join-Path $PSScriptRoot '.local-data/main-review/main-api/mobile.env'
if (-not (Test-Path -LiteralPath $configPath)) { throw 'Prepare the main Azure mobile configuration first.' }
$previous = @{}
try {
    foreach ($line in Get-Content -LiteralPath $configPath) {
        if ($line -match '^([A-Z][A-Z0-9_]*)=(.*)$') {
            $key = $Matches[1]
            $previous[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
            [Environment]::SetEnvironmentVariable($key, $Matches[2], 'Process')
        }
    }
    if ($env:CANOPY_TRIP_API_URL -ne 'https://func-canopy-dev-dxb0bgdgd6gghpd3.koreacentral-01.azurewebsites.net/api') {
        throw 'Unexpected main Azure destination.'
    }
    Push-Location (Join-Path $PSScriptRoot 'apps/ios')
    try { & npx.cmd expo start --go --lan --port $Port } finally { Pop-Location }
} finally {
    foreach ($key in $previous.Keys) { [Environment]::SetEnvironmentVariable($key, $previous[$key], 'Process') }
}
