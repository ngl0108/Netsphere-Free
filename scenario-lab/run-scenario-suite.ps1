param(
    [Parameter(Mandatory = $false)]
    [string]$FreeScenario = "free-enterprise-visibility",
    [Parameter(Mandatory = $false)]
    [string]$Password = "Password1!!@",
    [switch]$SyncRuntime
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$reportsDir = Join-Path $repoRoot "scenario-lab\reports"
$summaryPath = Join-Path $reportsDir "scenario-suite.latest.json"

if ($SyncRuntime) {
    & (Join-Path $PSScriptRoot "sync-scenario-runtime.ps1") -Target free
}

& (Join-Path $PSScriptRoot "seed-free-scenario.ps1") -Scenario $FreeScenario -Password $Password | Out-Null

& (Join-Path $repoRoot "Netsphere_Free_Deploy\preview-collector-local\smoke.ps1")
& (Join-Path $repoRoot "Netsphere_Free_Deploy\preview-collector-local\validate-contribution-flow.ps1")

$summary = [ordered]@{
    generated_at = (Get-Date).ToString("o")
    free_scenario = $FreeScenario
    free_report = "scenario-lab/reports/$FreeScenario.latest.json"
    smoke = "Netsphere_Free_Deploy/preview-collector-local/smoke.ps1"
    collector_validation = "Netsphere_Free_Deploy/preview-collector-local/validate-contribution-flow.ps1"
}

$summary | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 $summaryPath
Get-Content $summaryPath
