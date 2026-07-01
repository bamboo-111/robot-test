param(
    [string]$Distro = "Ubuntu-20.04",
    [string]$DeployDir = "",
    [string]$RepoDir = "/home/bamboo/kuavo_ws_src/kuavo-ros-opensource",
    [string]$Image = "kuavo-ros-opensource:master",
    [string]$Container = "kuavo5w_sim",
    [string]$RobotVersion = "62",
    [string]$Launch = "load_kuavo_mujoco_sim_wheel.launch",
    [switch]$RecreateContainer
)

$ErrorActionPreference = "Stop"

function Convert-WindowsPathToWsl {
    param([string]$Path)
    $resolved = (Resolve-Path -LiteralPath $Path).Path
    if ($resolved -notmatch "^([A-Za-z]):\\(.*)$") {
        throw "Only local drive paths are supported: $resolved"
    }
    $drive = $matches[1].ToLowerInvariant()
    $rest = $matches[2] -replace "\\", "/"
    return "/mnt/$drive/$rest"
}

function Invoke-Wsl {
    param([string]$Command)
    wsl -d $Distro -- bash -lc $Command
}

if (-not (Get-Command wsl -ErrorAction SilentlyContinue)) {
    throw "wsl was not found. Install WSL2 first."
}

if ([string]::IsNullOrWhiteSpace($DeployDir)) {
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    $DeployDir = Resolve-Path -LiteralPath (Join-Path $scriptDir "..\..")
}

$DeployDirWsl = Convert-WindowsPathToWsl $DeployDir

Write-Host "Distro: $Distro"
Write-Host "DeployDir: $DeployDirWsl"
Write-Host "RepoDir: $RepoDir"
Write-Host "Image: $Image"
Write-Host "Container: $Container"
Write-Host "ROBOT_VERSION: $RobotVersion"
Write-Host "Launch: $Launch"

$dockerCheck = Invoke-Wsl "docker info >/dev/null 2>&1; echo `$?"
if (($dockerCheck | Select-Object -Last 1).Trim() -ne "0") {
    throw "Docker is not reachable from $Distro. Start Docker Desktop and enable WSL integration."
}

$imageCheck = Invoke-Wsl "docker image inspect '$Image' >/dev/null 2>&1; echo `$?"
if (($imageCheck | Select-Object -Last 1).Trim() -ne "0") {
    throw "Docker image not found: $Image. Build it first with scripts/wsl/build-kuavo-image-retry.sh."
}

$repoCheck = Invoke-Wsl "[ -d '$RepoDir' ] && [ -d '$DeployDirWsl/scripts/container' ]; echo `$?"
if (($repoCheck | Select-Object -Last 1).Trim() -ne "0") {
    throw "Required directories were not found in WSL. Repo=$RepoDir Deploy=$DeployDirWsl"
}

if ($RecreateContainer) {
    Invoke-Wsl "docker rm -f '$Container' >/dev/null 2>&1 || true"
}

$running = Invoke-Wsl "docker inspect -f '{{.State.Running}}' '$Container' 2>/dev/null || echo missing"
$runningState = ($running | Select-Object -Last 1).Trim()

if ($runningState -eq "true") {
    $deployMountCheck = Invoke-Wsl "docker exec '$Container' test -d /root/kuavo_deploy/scripts/container; echo `$?"
    if (($deployMountCheck | Select-Object -Last 1).Trim() -ne "0") {
        Write-Host "Running container is missing /root/kuavo_deploy. Recreating it..."
        Invoke-Wsl "docker rm -f '$Container' >/dev/null 2>&1 || true"
        $runningState = "missing"
    }
}

if ($runningState -ne "true") {
    Write-Host "Starting container in background..."
    $startScriptTemplate = @'
set -euo pipefail
docker rm -f '__CONTAINER__' >/dev/null 2>&1 || true
if [ -e /dev/dxg ] && [ -d /usr/lib/wsl/lib ]; then
  echo WSL_GPU_MOUNTS_ENABLED
  docker run -d \
    --name '__CONTAINER__' \
    --net host --ipc host --privileged \
    --ulimit rtprio=99 --cap-add=sys_nice --group-add=dialout \
    --device=/dev/dxg \
    --gpus all \
    -e ROBOT_VERSION='__ROBOT_VERSION__' \
    -e DISABLE_ROS1_EOL_WARNINGS=1 \
    -e DISPLAY="${DISPLAY:-:0}" \
    -e WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}" \
    -e XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/mnt/wslg/runtime-dir}" \
    -e PULSE_SERVER="${PULSE_SERVER:-unix:/mnt/wslg/PulseServer}" \
    -e QT_X11_NO_MITSHM=1 \
    -e LD_LIBRARY_PATH=/usr/lib/wsl/lib \
    -v /usr/lib/wsl:/usr/lib/wsl:ro \
    -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
    -v /mnt/wslg:/mnt/wslg \
    -v /dev:/dev \
    -v "$HOME/.ros:/root/.ros" \
    -v "$HOME/.config/lejuconfig:/root/.config/lejuconfig" \
    -v '__REPO_DIR__:/root/kuavo_ws' \
    -v '__DEPLOY_DIR__:/root/kuavo_deploy:ro' \
    '__IMAGE__' \
    tail -f /dev/null >/dev/null
else
  echo WSL_GPU_MOUNTS_DISABLED
  docker run -d \
    --name '__CONTAINER__' \
    --net host --ipc host --privileged \
    --ulimit rtprio=99 --cap-add=sys_nice --group-add=dialout \
    -e ROBOT_VERSION='__ROBOT_VERSION__' \
    -e DISABLE_ROS1_EOL_WARNINGS=1 \
    -e DISPLAY="${DISPLAY:-:0}" \
    -e WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}" \
    -e XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/mnt/wslg/runtime-dir}" \
    -e PULSE_SERVER="${PULSE_SERVER:-unix:/mnt/wslg/PulseServer}" \
    -e QT_X11_NO_MITSHM=1 \
    -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
    -v /mnt/wslg:/mnt/wslg \
    -v /dev:/dev \
    -v "$HOME/.ros:/root/.ros" \
    -v "$HOME/.config/lejuconfig:/root/.config/lejuconfig" \
    -v '__REPO_DIR__:/root/kuavo_ws' \
    -v '__DEPLOY_DIR__:/root/kuavo_deploy:ro' \
    '__IMAGE__' \
    tail -f /dev/null >/dev/null
fi
'@
    $startScript = $startScriptTemplate.Replace("__CONTAINER__", $Container).
        Replace("__ROBOT_VERSION__", $RobotVersion).
        Replace("__REPO_DIR__", $RepoDir).
        Replace("__DEPLOY_DIR__", $DeployDirWsl).
        Replace("__IMAGE__", $Image)
    Invoke-Wsl $startScript | Out-Host
}
else {
    Write-Host "Container is already running."
}

$openvinoCheck = Invoke-Wsl @"
docker exec '$Container' bash -lc '
set -e
source /root/kuavo_ws/installed/setup.bash
source /root/kuavo_ws/devel/setup.bash
export LD_LIBRARY_PATH="/opt/drake/lib:/usr/lib:${LD_LIBRARY_PATH:-}"
ldd /root/kuavo_ws/devel/lib/libnodelet_controller.so | grep -q "libopenvino.so.2520 => not found" && exit 42
exit 0
'
"@
if ($LASTEXITCODE -eq 42) {
    throw "libopenvino.so.2520 is missing in the container. Install OpenVINO runtime before launching nodelet_controller."
}

Write-Host "Starting MuJoCo launch. Press Ctrl+C here to stop roslaunch."
$launchScript = "cd /root/kuavo_ws && export ROBOT_VERSION='$RobotVersion' DISABLE_ROS1_EOL_WARNINGS=1 && KUAVO_LAUNCH='$Launch' KUAVO_LAUNCH_ARGS='output_system_info:=false robot_type:=2 rviz:=false visualize_humanoid:=false' bash /root/kuavo_deploy/scripts/container/start-kuavo5w-mujoco.sh"
wsl -d $Distro -- docker exec -it $Container bash -lc $launchScript
