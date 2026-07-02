param(
    [string]$Distro = "Ubuntu-20.04",
    [string]$Container = "kuavo5w_sim"
)

$ErrorActionPreference = "Stop"
$TimingEnabled = $env:KUAVO_TIMING -eq "1"

function Write-Timing {
    param([string]$Phase)
    if ($TimingEnabled) {
        $elapsedMs = [Math]::Round(([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()), 3)
        Write-Host "[TIMING] source=restore phase=$Phase t_ms=$elapsedMs"
    }
}

Write-Timing "restore_script_start"

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

Write-Timing "restore_script_end"
exit $LASTEXITCODE
