param(
    [switch]$Restart
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$platformScript = Join-Path $scriptDir "start-kuavo5w-platform.ps1"

if (-not (Test-Path -LiteralPath $platformScript)) {
    throw "Missing platform script: $platformScript"
}

$args = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", $platformScript,
    "-ReadyTimeoutSeconds", "60"
)

if ($Restart) {
    $args += "-StopExistingLaunch"
}

& powershell @args
exit $LASTEXITCODE
