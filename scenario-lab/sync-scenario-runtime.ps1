param(
    [Parameter(Mandatory = $false)]
    [ValidateSet("free")]
    [string]$Target = "free"
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")

function Sync-FreeRuntime {
    Write-Host "Syncing FREE collector-local runtime..." -ForegroundColor Cyan
    Push-Location $repoRoot
    try {
        docker compose -p netsphere-preview-collector -f docker-compose.preview-collector-local.yml build collector-local
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to build FREE collector-local runtime."
        }
        docker compose -p netsphere-preview-collector -f docker-compose.preview-collector-local.yml up -d collector-local
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to start FREE collector-local runtime."
        }
    }
    finally {
        Pop-Location
    }
}

if ($Target -eq "free") {
    Sync-FreeRuntime
}

Write-Host "Scenario runtime sync complete." -ForegroundColor Green
