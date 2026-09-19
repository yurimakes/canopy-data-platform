param([string]$Inputs = '', [switch]$CommuteVerified)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (Test-Path '.local-data/runtime/java/bin/java.exe') { $env:JAVA_HOME = Join-Path $PSScriptRoot '.local-data/runtime/java' }
if (!$Inputs) {
    & ./.venv/Scripts/python.exe tools/local/client.py export
    if ($LASTEXITCODE -ne 0) { throw 'Start the local API before running Weekly.' }
}
$arguments = @('tools/local/weekly.py')
if ($Inputs) { $arguments += @('--inputs', $Inputs) }
if ($CommuteVerified) { $arguments += '--commute-verified' }
& ./.venv/Scripts/python.exe @arguments
exit $LASTEXITCODE
