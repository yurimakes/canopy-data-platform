param(
    [string]$SubscriptionId = "27db5ec6-d206-4028-b5e1-6004dca5eeef",
    [string]$ResourceGroup = "5dt-2nd-team1",
    [string]$FunctionAppName = "func-canopy-dev"
)

$ErrorActionPreference = "Stop"

$functionRoot = Split-Path -Parent $PSScriptRoot
$verifyScript = Join-Path $PSScriptRoot "verify_carbon_smoke.ps1"

Write-Host "[1/7] Checking Azure CLI login..."
$account = az account show --output json 2>$null | ConvertFrom-Json
if (-not $account) {
    throw "Azure CLI login not found. Run 'az login' first."
}

Write-Host "[2/7] Selecting Canopy subscription..."
az account set --subscription $SubscriptionId
$currentSub = az account show --query id -o tsv
if ($currentSub -ne $SubscriptionId) {
    throw "Unexpected subscription selected: $currentSub"
}

Write-Host "[3/7] Checking required tools..."
if (-not (Get-Command func -ErrorAction SilentlyContinue)) {
    throw "Azure Functions Core Tools command 'func' was not found."
}
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python command was not found."
}

Push-Location $functionRoot
try {
    Write-Host "[4/7] Running carbon unit tests..."
    python -m pip install -r requirements-dev.txt
    python -m pytest -q tests\test_carbon_calculator.py
    if ($LASTEXITCODE -ne 0) {
        throw "Carbon unit tests failed. Deployment stopped."
    }

    Write-Host "[5/7] Publishing the whole func-canopy-dev deployment unit..."
    func azure functionapp publish $FunctionAppName
    if ($LASTEXITCODE -ne 0) {
        throw "Azure Functions publish failed."
    }
}
finally {
    Pop-Location
}

Write-Host "Waiting briefly for the deployment to become active..."
Start-Sleep -Seconds 15

Write-Host "[6/7] Checking deployed Functions and preparing authenticated smoke URL..."
$functionNames = az functionapp function list `
    --resource-group $ResourceGroup `
    --name $FunctionAppName `
    --query "[].name" `
    -o tsv

$functionNames | ForEach-Object { Write-Host "  $_" }
if (($functionNames -join "`n") -notmatch "carbon") {
    throw "carbon-smoke Function was not found after deployment."
}

$hostName = az functionapp show `
    --resource-group $ResourceGroup `
    --name $FunctionAppName `
    --query "defaultHostName" `
    -o tsv

$functionKey = az functionapp keys list `
    --resource-group $ResourceGroup `
    --name $FunctionAppName `
    --query "functionKeys.default" `
    -o tsv

if (-not $hostName) {
    throw "Could not resolve Function App hostname."
}
if (-not $functionKey) {
    throw "Could not retrieve the default Function key."
}

$carbonUrl = "https://$hostName/api/carbon-smoke?code=$functionKey"

Write-Host "[7/7] Calling carbon-smoke in Azure..."
& $verifyScript -FunctionUrl $carbonUrl
if ($LASTEXITCODE -ne 0) {
    throw "Azure carbon-smoke verification failed."
}

Write-Host ""
Write-Host "PASS: Carbon policy/calculator is deployed and verified in func-canopy-dev."
Write-Host "Azure-to-Azure authentication remains Managed Identity/RBAC."
Write-Host "The HTTP Function key was used only to call the FUNCTION-auth smoke endpoint."
Write-Host "No post-test code change is required for this WBS if this script completes successfully."
Write-Host "The final client-facing Trip result API is a separate follow-up task."
