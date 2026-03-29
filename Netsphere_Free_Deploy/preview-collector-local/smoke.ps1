param()

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "..\_common.ps1")

Assert-HttpStatus -Url "http://127.0.0.1:18080/api/v1/auth/bootstrap/status" -Label "collector-local bootstrap status"
