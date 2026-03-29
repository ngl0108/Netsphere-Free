param()

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "..\_common.ps1")

Assert-HttpStatus -Url "http://localhost:18080/api/v1/auth/bootstrap/status" -Label "collector-local bootstrap status"
