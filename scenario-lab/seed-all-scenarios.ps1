param(
    [Parameter(Mandatory = $false)]
    [ValidateSet("all", "pro", "free")]
    [string]$Target = "all",
    [Parameter(Mandatory = $false)]
    [string]$Password = "Password1!!@"
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$summaryPath = Join-Path $repoRoot "scenario-lab\reports\scenario-seed-all.latest.json"

function Get-ScenarioSlugs {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Edition
    )

    $dir = Join-Path $repoRoot "scenario-lab\scenarios\$Edition"
    if (-not (Test-Path $dir)) {
        return @()
    }
    return Get-ChildItem -Path $dir -Filter *.json |
        Sort-Object Name |
        ForEach-Object { $_.BaseName }
}

$summary = [ordered]@{
    generated_at = (Get-Date).ToString("o")
    target = $Target
    password = $Password
    pro = @()
    free = @()
}

if ($Target -in @("all", "pro")) {
    foreach ($slug in Get-ScenarioSlugs -Edition "pro") {
        & (Join-Path $PSScriptRoot "seed-pro-scenario.ps1") -Scenario $slug -Password $Password | Out-Null
        $summary.pro += $slug
    }
}

if ($Target -in @("all", "free")) {
    foreach ($slug in Get-ScenarioSlugs -Edition "free") {
        & (Join-Path $PSScriptRoot "seed-free-scenario.ps1") -Scenario $slug -Password $Password | Out-Null
        $summary.free += $slug
    }
}

$summary | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 $summaryPath
Get-Content $summaryPath
