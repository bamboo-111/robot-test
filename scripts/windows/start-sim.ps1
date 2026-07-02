param(
    [switch]$Restart
)

$ErrorActionPreference = "Stop"

Write-Host "Compatibility entry: daily experiments should start from the Web console."
Write-Host "Forwarding to GUI simulation startup because action experiments need visual confirmation."

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$platformScript = Join-Path $scriptDir "start-kuavo5w-platform.ps1"

if (-not (Test-Path -LiteralPath $platformScript)) {
    throw "Missing platform script: $platformScript"
}

$args = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", $platformScript,
    "-VisualizeHumanoid",
    "-ReadyTimeoutSeconds", "60"
)

if ($Restart) {
    $args += "-StopExistingLaunch"
}

& powershell @args
exit $LASTEXITCODE
