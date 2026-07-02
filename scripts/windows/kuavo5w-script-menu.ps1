param(
    [string]$Distro = "Ubuntu-20.04",
    [string]$Container = "kuavo5w_sim",
    [string]$RobotVersion = "62",
    [string]$Launch = "load_kuavo_mujoco_sim_wheel.launch"
)

$ErrorActionPreference = "Stop"

Write-Host "Fallback entry: prefer scripts/windows/start-kuavo5w-web-control.ps1 for daily experiments."
Write-Host "This menu is kept for no-browser or emergency operator fallback."

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path -LiteralPath (Join-Path $scriptDir "..\..")
$platformScript = Join-Path $scriptDir "start-kuavo5w-platform.ps1"
$restoreScript = Join-Path $scriptDir "kuavo5w-restore.ps1"
$scenarioDir = Join-Path $repoRoot "kuavo_sim_platform\scenarios"

function Invoke-Platform {
    param([string[]]$ExtraArgs)

    $args = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $platformScript,
        "-Distro", $Distro,
        "-Container", $Container,
        "-RobotVersion", $RobotVersion,
        "-Launch", $Launch
    ) + $ExtraArgs

    & powershell @args
}

function Show-Menu {
    Clear-Host
    Write-Host "Kuavo 5-W Script Menu"
    Write-Host ""
    Write-Host "1  Start/connect simulator"
    Write-Host "2  Run safe probe"
    Write-Host "3  Run base forward demo"
    Write-Host "4  Choose YAML scenario"
    Write-Host "R  Restore / stop / NoControl"
    Write-Host "L  Tail MuJoCo launch log"
    Write-Host "C  Attach container shell"
    Write-Host "Q  Quit"
    Write-Host ""
    Write-Host "Emergency command from another PowerShell:"
    Write-Host "  powershell -NoProfile -ExecutionPolicy Bypass -File scripts/windows/kuavo5w-restore.ps1"
    Write-Host ""
}

function Invoke-Restore {
    & powershell -NoProfile -ExecutionPolicy Bypass -File $restoreScript `
        -Distro $Distro `
        -Container $Container
}

function Choose-Scenario {
    if (-not (Test-Path -LiteralPath $scenarioDir)) {
        Write-Host "Scenario directory not found: $scenarioDir"
        return
    }

    $files = @(Get-ChildItem -LiteralPath $scenarioDir -Filter "*.yaml" -File | Sort-Object Name)
    if ($files.Count -eq 0) {
        Write-Host "No scenario YAML files found in $scenarioDir"
        return
    }

    Write-Host ""
    Write-Host "Available scenarios:"
    for ($i = 0; $i -lt $files.Count; $i++) {
        Write-Host ("{0}. {1}" -f ($i + 1), $files[$i].Name)
    }
    Write-Host ""
    $text = Read-Host "Select scenario number, or press Enter to cancel"
    if ([string]::IsNullOrWhiteSpace($text)) {
        return
    }
    $number = 0
    if (-not [int]::TryParse($text, [ref]$number) -or $number -lt 1 -or $number -gt $files.Count) {
        Write-Host "Invalid selection."
        return
    }

    $selected = $files[$number - 1]
    $scenarioPath = "/root/kuavo_deploy/kuavo_sim_platform/scenarios/$($selected.Name)"
    Invoke-Platform @("-Scenario", $scenarioPath)
}

$done = $false
while (-not $done) {
    Show-Menu
    $choice = Read-Host "Select"
    if ($null -eq $choice) {
        break
    }
    switch ($choice.Trim().ToUpperInvariant()) {
        "1" { Invoke-Platform @("-ReadyTimeoutSeconds", "30") }
        "2" { Invoke-Platform @("-RunProbe", "-ReadyTimeoutSeconds", "30") }
        "3" { Invoke-Platform @("-Demo", "forward", "-ReadyTimeoutSeconds", "30") }
        "4" { Choose-Scenario }
        "R" { Invoke-Restore }
        "L" { wsl -d $Distro -- docker exec -it $Container bash -lc "tail -120 /tmp/kuavo5w_mujoco_start.log" }
        "C" { wsl -d $Distro -- docker exec -it $Container bash }
        "Q" { $done = $true }
        default { Write-Host "Unknown selection." }
    }
    if ($done) {
        break
    }
    Write-Host ""
    Read-Host "Press Enter to return to menu"
}
