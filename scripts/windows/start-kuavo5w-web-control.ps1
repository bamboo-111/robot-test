param(
    [int]$Port = 8765,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path -LiteralPath (Join-Path $scriptDir "..\..")
$server = Join-Path $repoRoot "kuavo_sim_platform\web_control\server.py"

if (-not (Test-Path -LiteralPath $server)) {
    throw "Web control server was not found: $server"
}

$url = "http://127.0.0.1:$Port"
Write-Host "Starting Kuavo web control at $url"

if (-not $NoBrowser) {
    Start-Process $url
}

python $server --host 127.0.0.1 --port $Port
