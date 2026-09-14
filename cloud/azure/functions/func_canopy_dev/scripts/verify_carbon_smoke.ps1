param(
    [Parameter(Mandatory = $true)]
    [string]$FunctionUrl
)

$ErrorActionPreference = "Stop"

function Invoke-CarbonCase {
    param(
        [string]$Name,
        [object]$Segments,
        [double]$Expected
    )

    $body = @{ segments = $Segments } | ConvertTo-Json -Depth 10

    $result = Invoke-RestMethod `
        -Method POST `
        -Uri $FunctionUrl `
        -ContentType "application/json" `
        -Body $body

    if ($result.status -ne "PASS") {
        throw "$Name failed: status=$($result.status)"
    }

    $actual = [double]$result.emission_kgco2e
    if ([math]::Abs($actual - $Expected) -gt 0.000001) {
        throw "$Name failed: expected=$Expected actual=$actual"
    }

    if ($result.factor_version -ne "2026_v1") {
        throw "$Name failed: unexpected factor_version=$($result.factor_version)"
    }

    if ($result.policy_version -ne "carbon-policy-v1") {
        throw "$Name failed: unexpected policy_version=$($result.policy_version)"
    }

    if ($result.mode_source -ne "predicted_mode") {
        throw "$Name failed: unexpected mode_source=$($result.mode_source)"
    }

    if ($result.user_confirmation_applied -ne $false) {
        throw "$Name failed: user_confirmation_applied must be false"
    }

    Write-Host "PASS $Name emission_kgco2e=$actual factor_version=$($result.factor_version) policy_version=$($result.policy_version) mode_source=$($result.mode_source)"
}

Invoke-CarbonCase `
    -Name "multi-segment" `
    -Expected 0.6276 `
    -Segments @(
        @{ segment_id = "seg-1"; predicted_mode = "walk"; distance_m = 400 },
        @{ segment_id = "seg-2"; predicted_mode = "bus"; distance_m = 5000 },
        @{ segment_id = "seg-3"; predicted_mode = "walk"; distance_m = 300 }
    )

Invoke-CarbonCase `
    -Name "predicted-car-3km" `
    -Expected 0.49773 `
    -Segments @(
        @{ segment_id = "seg-car"; predicted_mode = "car"; distance_m = 3000 }
    )

Write-Host "Carbon Functions integration verification completed."
