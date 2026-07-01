param(
    [string]$Distro = "Ubuntu-20.04",
    [string]$Container = "kuavo5w_sim"
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$platformScript = Join-Path $scriptDir "start-kuavo5w-platform.ps1"

if (-not (Test-Path -LiteralPath $platformScript)) {
    throw "start-kuavo5w-platform.ps1 was not found next to this script."
}

Write-Host "Restoring Kuavo 5-W to a safe state..."
Write-Host "Action: publish zero base velocity, then switch to NoControl."

& powershell -NoProfile -ExecutionPolicy Bypass -File $platformScript `
    -Distro $Distro `
    -Container $Container `
    -Demo stop `
    -ReadyTimeoutSeconds 30

exit $LASTEXITCODE
