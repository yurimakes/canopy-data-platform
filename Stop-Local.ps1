$ErrorActionPreference = 'Stop'
$scriptPath = (Join-Path $PSScriptRoot 'tools/local/server.py').Replace('/', '\')
$appRoot = (Join-Path $PSScriptRoot 'apps/ios').Replace('/', '\')
$localProcesses = Get-CimInstance Win32_Process | Where-Object {
    if (!$_.CommandLine) { return $false }
    $command = $_.CommandLine.Replace('/', '\')
    ($_.Name -eq 'python.exe' -and $command.Contains($scriptPath)) -or
    ($_.Name -eq 'node.exe' -and $command.Contains($appRoot) -and $command -match 'expo.*start.*--port 8082')
}
foreach ($process in $localProcesses) { Stop-Process -Id $process.ProcessId -ErrorAction SilentlyContinue }
$pidFile = Join-Path $PSScriptRoot '.local-data/server.pid'
if (Test-Path $pidFile) { Remove-Item -LiteralPath $pidFile }
Write-Host 'Canopy local API and UI stopped.'
