param(
    [Parameter(Mandatory = $false)]
    [ValidateSet("all", "pro", "free")]
    [string]$Target = "all"
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$frontendRoot = Join-Path $repoRoot "Netsphere_Free_Frontend"
$reportsDir = Join-Path $repoRoot "scenario-lab\reports"
$summaryPath = Join-Path $reportsDir "scenario-deep-e2e.latest.json"

Push-Location $frontendRoot
try {
    $summary = [ordered]@{
        generated_at = (Get-Date).ToString("o")
        target = $Target
        runs = @()
    }

    $env:PW_SKIP_WEBSERVER = "1"

    if ($Target -in @("all", "free")) {
        & node .\node_modules\@playwright\test\cli.js test tests/e2e/scenario-lab-free-actions.spec.js
        if ($LASTEXITCODE -ne 0) {
            throw "Scenario-lab FREE deep E2E failed."
        }
        $summary.runs += [ordered]@{
            scope = "free"
            base_url = "http://127.0.0.1:18080"
            runner = "tests/e2e/scenario-lab-free-actions.spec.js"
        }
    }

    if ($Target -in @("all", "pro")) {
        & node .\node_modules\@playwright\test\cli.js test tests/e2e/scenario-lab-pro-actions.spec.js
        if ($LASTEXITCODE -ne 0) {
            throw "Scenario-lab PRO deep E2E failed."
        }
        $summary.runs += [ordered]@{
            scope = "pro"
            base_url = "http://localhost"
            runner = "tests/e2e/scenario-lab-pro-actions.spec.js"
        }
    }

    $summary | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 $summaryPath
    Get-Content $summaryPath
}
finally {
    Remove-Item Env:PW_SKIP_WEBSERVER -ErrorAction SilentlyContinue
    Pop-Location
}
