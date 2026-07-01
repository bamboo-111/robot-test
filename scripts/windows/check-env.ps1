param(
    [string]$ExpectedDistroPattern = "Ubuntu",
    [string]$PreferredUbuntuVersionPattern = "Ubuntu-(20\.04|22\.04)"
)

$ErrorActionPreference = "Continue"

function Write-Section {
    param([string]$Title)
    Write-Host ""
    Write-Host "== $Title =="
}

function Test-CommandAvailable {
    param([string]$Name)
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Invoke-Checked {
    param(
        [string]$Label,
        [string]$Command,
        [string[]]$Arguments
    )

    Write-Host "`n[$Label] $Command $($Arguments -join ' ')"
    if (-not (Test-CommandAvailable $Command)) {
        Write-Warning "$Command is not installed or is not on PATH."
        return $null
    }

    try {
        $output = & $Command @Arguments 2>&1
        $exitCode = $LASTEXITCODE
        if ($null -ne $output) {
            $output | ForEach-Object { Write-Host $_ }
        }
        if ($exitCode -ne 0) {
            Write-Warning "$Command exited with code $exitCode."
        }
        return [pscustomobject]@{
            Output = $output
            ExitCode = $exitCode
        }
    }
    catch {
        Write-Warning $_.Exception.Message
        return $null
    }
}

function Convert-ToPlainText {
    param([object]$Value)

    if ($null -eq $Value) {
        return ""
    }

    $text = ($Value | Out-String)
    return ($text -replace "`0", "" -replace "\s+", " ").Trim()
}

Write-Section "WSL"
$wslAvailable = Test-CommandAvailable "wsl"
if (-not $wslAvailable) {
    Write-Warning "WSL is not installed. Install it first: wsl --install -d Ubuntu-22.04"
}
else {
    Invoke-Checked "wsl status" "wsl" @("--status") | Out-Null
    Invoke-Checked "wsl version" "wsl" @("--version") | Out-Null
    $wslList = Invoke-Checked "wsl distros" "wsl" @("-l", "-v")

    if ($null -ne $wslList -and $null -ne $wslList.Output) {
        $listText = Convert-ToPlainText $wslList.Output
        if ($listText -notmatch $ExpectedDistroPattern) {
            Write-Warning "No distro matching '$ExpectedDistroPattern' was found. Install Ubuntu 22.04 or Ubuntu 20.04."
        }
        elseif ($listText -notmatch $PreferredUbuntuVersionPattern) {
            Write-Warning "Ubuntu was found, but Ubuntu 20.04/22.04 was not clearly detected. Existing newer Ubuntu distros can be used as the WSL/Docker host, but Ubuntu 22.04 is the recommended default."
        }
        if ($listText -match "Ubuntu" -and $listText -notmatch "\b2\b") {
            Write-Warning "Ubuntu was found, but WSL version 2 was not clearly detected. Use: wsl --set-version <DistroName> 2"
        }
    }
}

Write-Section "Docker"
if (-not (Test-CommandAvailable "docker")) {
    Write-Warning "Docker is not installed or not on PATH."
    Write-Host "Install Docker Desktop for Windows, then enable:"
    Write-Host "- Settings > General > Use the WSL 2 based engine"
    Write-Host "- Settings > Resources > WSL Integration > your Ubuntu distro"
    Write-Host "- Linux containers mode"
    exit 0
}

Invoke-Checked "docker version" "docker" @("--version") | Out-Null
$dockerInfo = Invoke-Checked "docker info" "docker" @("info", "--format", "{{.OSType}} / {{.OperatingSystem}}")
if ($null -eq $dockerInfo -or $dockerInfo.ExitCode -ne 0) {
    Write-Warning "Docker CLI is installed, but Docker daemon is not reachable. Start Docker Desktop and retry."
    exit 0
}

$dockerText = Convert-ToPlainText $dockerInfo.Output
if ($dockerText -match "^windows\b") {
    Write-Warning "Docker is using Windows containers. Switch Docker Desktop to Linux containers."
}
elseif ($dockerText -match "^linux\b") {
    Write-Host "Docker is using Linux containers: $dockerText"
}
else {
    Write-Warning "Could not determine Docker container mode from: $dockerText"
}

Write-Section "Next Steps"
Write-Host "If WSL2, Ubuntu integration, and Docker Linux containers are ready, continue in WSL Ubuntu:"
Write-Host "bash scripts/wsl/clone-kuavo.sh"
