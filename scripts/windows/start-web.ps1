param(
    [int]$Port = 8765
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$webScript = Join-Path $scriptDir "start-kuavo5w-web-control.ps1"

if (-not (Test-Path -LiteralPath $webScript)) {
    throw "Missing web control script: $webScript"
}

& powershell -NoProfile -ExecutionPolicy Bypass -File $webScript -Port $Port
exit $LASTEXITCODE
