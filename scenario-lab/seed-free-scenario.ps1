param(
    [Parameter(Mandatory = $false)]
    [string]$Scenario = "free-enterprise-visibility",
    [Parameter(Mandatory = $false)]
    [string]$Password = "Password1!!@",
    [switch]$NoWipe
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$scenarioPath = "/app/scenario-lab/scenarios/free/$Scenario.json"
$reportPath = Join-Path $repoRoot "scenario-lab\reports\$Scenario.latest.json"

$arguments = @(
    "-p", "netsphere-preview-collector",
    "-f", "docker-compose.preview-collector-local.yml",
    "exec", "-T", "collector-local",
    "sh", "-lc",
    "PYTHONPATH=/app python /app/tools/seed_scenario_lab.py --scenario-file $scenarioPath --user-password '$Password'$(if ($NoWipe) { '' } else { ' --wipe-existing' })"
)

$result = docker compose @arguments 2>&1
$result | Set-Content -Encoding UTF8 $reportPath
if ($LASTEXITCODE -ne 0) {
    throw "FREE scenario seeding failed for '$Scenario'. See $reportPath for captured output."
}
$result
