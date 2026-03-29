param(
    [Parameter(Mandatory = $false)]
    [ValidateSet("all", "pro", "free")]
    [string]$Target = "all"
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$frontendRoot = Join-Path $repoRoot "Netsphere_Free_Frontend"
$reportsDir = Join-Path $repoRoot "scenario-lab\reports"
$summaryPath = Join-Path $reportsDir "scenario-e2e.latest.json"

Push-Location $frontendRoot
try {
    $summary = [ordered]@{
        generated_at = (Get-Date).ToString("o")
        target = $Target
        runs = @()
    }

    if ($Target -in @("all", "pro")) {
        $env:E2E_BASE_URL = "http://localhost"
        & node .\node_modules\@playwright\test\cli.js test tests/e2e/scenario-lab-pro-live.spec.js
        if ($LASTEXITCODE -ne 0) {
            throw "Scenario-lab PRO live spec failed."
        }
        $summary.runs += [ordered]@{
            scope = "pro"
            base_url = "http://localhost"
            runner = "tests/e2e/scenario-lab-pro-live.spec.js"
        }
    }

    if ($Target -in @("all", "free")) {
        $env:E2E_BASE_URL = "http://127.0.0.1:18080"
        & node .\node_modules\@playwright\test\cli.js test tests/e2e/scenario-lab-free-live.spec.js
        if ($LASTEXITCODE -ne 0) {
            throw "Scenario-lab FREE live spec failed."
        }
        $summary.runs += [ordered]@{
            scope = "free"
            base_url = "http://127.0.0.1:18080"
            runner = "tests/e2e/scenario-lab-free-live.spec.js"
        }
    }

    $summary | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 $summaryPath
    Get-Content $summaryPath
}
finally {
    Remove-Item Env:E2E_BASE_URL -ErrorAction SilentlyContinue
    Pop-Location
}
