param([string]$ApiHost = "", [int]$Port = 8010)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$python = Join-Path $PSScriptRoot ".venv/Scripts/python.exe"
if (!(Test-Path $python)) { throw "Run Setup-Local.cmd first." }
if (!$ApiHost) {
    $ApiHost = Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -match '^(192\.168\.|10\.|172\.(1[6-9]|2[0-9]|3[01])\.)' -and $_.InterfaceAlias -notmatch 'vEthernet|Virtual|Docker|WSL' } | Select-Object -First 1 -ExpandProperty IPAddress
    if (!$ApiHost) { $ApiHost = "127.0.0.1" }
}
New-Item -ItemType Directory -Force .local-data | Out-Null
try { $status = Invoke-RestMethod "http://127.0.0.1:$Port/api/local/status" -TimeoutSec 2 } catch { $status = $null }
if ($status -and $status.data_directory -ne (Join-Path $PSScriptRoot '.local-data')) { throw "Port is used by another project." }
if (!$status) {
    $process = Start-Process -FilePath $python -ArgumentList @(('"{0}"' -f (Join-Path $PSScriptRoot 'tools/local/server.py')),'--port', $Port) -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput '.local-data/api.log' -RedirectStandardError '.local-data/api-error.log'
    $process.Id | Set-Content .local-data/server.pid
    for ($i=0; $i -lt 30; $i++) {
        Start-Sleep -Milliseconds 500
        try { $status = Invoke-RestMethod "http://127.0.0.1:$Port/api/local/status" -TimeoutSec 1; break } catch {}
    }
    if (!$status) { throw "API startup failed. Check .local-data/api-error.log" }
}
$settings = Get-Content .local-data/local-settings.json | ConvertFrom-Json
$env:CANOPY_LOCAL_ONLY = 'true'
$env:CANOPY_TRIP_API_URL = "http://${ApiHost}:$Port/api"
$env:CANOPY_GPS_FUNCTION_KEY = $settings.gps_key
$env:CANOPY_TRIP_FUNCTION_KEY = ''
$env:CANOPY_UI_PREVIEW = 'false'
$env:EXPO_NO_DOTENV = '1'
Write-Host "Local API: $env:CANOPY_TRIP_API_URL"
Write-Host 'Developer ID: canopydev'
Write-Host "Developer password: $($settings.developer_password)"
Write-Host 'iPhone and PC must be on the same Wi-Fi. Stop-Local.cmd stops the API.'
Set-Location apps/ios
& npm.cmd start -- --port 8082
