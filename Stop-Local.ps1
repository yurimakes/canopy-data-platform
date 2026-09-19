$ErrorActionPreference = 'Stop'
$scriptPath = Join-Path $PSScriptRoot 'tools/local/server.py'
$matches = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like "*$scriptPath*" }
foreach ($process in $matches) { Stop-Process -Id $process.ProcessId -ErrorAction SilentlyContinue }
$pidFile = Join-Path $PSScriptRoot '.local-data/server.pid'
if (Test-Path $pidFile) { Remove-Item -LiteralPath $pidFile }
Write-Host 'API stopped. Press Ctrl+C in the Expo window to stop the UI server.'
