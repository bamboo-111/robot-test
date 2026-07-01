param(
    [string]$Distro = "Ubuntu-20.04",
    [string]$DeployDir = "",
    [string]$RepoDir = "/home/bamboo/kuavo_ws_src/kuavo-ros-opensource",
    [string]$Image = "kuavo-ros-opensource:master",
    [string]$Container = "kuavo5w_sim",
    [string]$RobotVersion = "62",
    [string]$Launch = "load_kuavo_mujoco_sim_wheel.launch",
    [switch]$RecreateContainer,
    [switch]$StopExistingLaunch,
    [switch]$VisualizeHumanoid,
    [switch]$RunProbe,
    [ValidateSet("", "probe", "forward", "stop")]
    [string]$Demo = "",
    [string]$Scenario = "",
    [string]$Script = "",
    [int]$ReadyTimeoutSeconds = 60
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

function Invoke-Container {
    param([string]$Command)
    wsl -d $Distro -- docker exec $Container bash -lc $Command
}

function Invoke-ContainerScript {
    param(
        [string]$Script,
        [string]$RemotePath = "/tmp/kuavo_platform_step.sh"
    )
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($Script)
    $encoded = [Convert]::ToBase64String($bytes)
    wsl -d $Distro -- docker exec $Container bash -lc "printf '%s' '$encoded' | base64 -d > '$RemotePath' && chmod +x '$RemotePath' && bash '$RemotePath'"
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
Write-Host "VisualizeHumanoid: $($VisualizeHumanoid.IsPresent)"

$dockerCheck = Invoke-Wsl "docker info >/dev/null 2>&1; echo `$?"
if (($dockerCheck | Select-Object -Last 1).Trim() -ne "0") {
    throw "Docker is not reachable from $Distro. Start Docker Desktop and enable WSL integration."
}

$imageCheck = Invoke-Wsl "docker image inspect '$Image' >/dev/null 2>&1; echo `$?"
if (($imageCheck | Select-Object -Last 1).Trim() -ne "0") {
    throw "Docker image not found: $Image. Build it first with scripts/wsl/build-kuavo-image-retry.sh."
}

$pathCheck = Invoke-Wsl "[ -d '$RepoDir' ] && [ -d '$DeployDirWsl/kuavo_sim_platform' ] && [ -d '$DeployDirWsl/scripts/container' ]; echo `$?"
if (($pathCheck | Select-Object -Last 1).Trim() -ne "0") {
    throw "Required directories were not found in WSL. Repo=$RepoDir Deploy=$DeployDirWsl"
}

if ($RecreateContainer) {
    Invoke-Wsl "docker rm -f '$Container' >/dev/null 2>&1 || true"
}

$running = Invoke-Wsl "docker inspect -f '{{.State.Running}}' '$Container' 2>/dev/null || echo missing"
$runningState = ($running | Select-Object -Last 1).Trim()

if ($runningState -eq "true") {
    $deployMountCheck = Invoke-Wsl "docker exec '$Container' test -d /root/kuavo_deploy/kuavo_sim_platform; echo `$?"
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

$openvinoCheck = Invoke-ContainerScript -RemotePath "/tmp/kuavo_platform_check_openvino.sh" -Script @'
set -e
source /root/kuavo_ws/installed/setup.bash
source /root/kuavo_ws/devel/setup.bash
export LD_LIBRARY_PATH="/opt/drake/lib:/usr/lib:${LD_LIBRARY_PATH:-}"
ldd /root/kuavo_ws/devel/lib/libnodelet_controller.so | grep -q 'libopenvino.so.2520 => not found' && exit 42
exit 0
'@
if ($LASTEXITCODE -eq 42) {
    throw "libopenvino.so.2520 is missing in the container. Install OpenVINO runtime before launching nodelet_controller."
}

if ($StopExistingLaunch) {
    Write-Host "Stopping existing ROS launch processes..."
    Invoke-ContainerScript -RemotePath "/tmp/kuavo_platform_stop_launch.sh" -Script @'
set +e
pkill -f '[r]oslaunch' || true
pkill -f '[r]oscore' || true
pkill -f '[r]osmaster' || true
rm -f /tmp/kuavo5w_mujoco.pid
sleep 1
echo stopped
'@ | Out-Host
}

$launchRunning = Invoke-ContainerScript -RemotePath "/tmp/kuavo_platform_pid_check.sh" -Script @'
set +e
if test -f /tmp/kuavo5w_mujoco.pid; then
  pid="$(cat /tmp/kuavo5w_mujoco.pid 2>/dev/null)"
  if test -n "$pid"; then
    if test -r "/proc/$pid/cmdline"; then
      cmdline="$(tr '\000' ' ' < "/proc/$pid/cmdline")"
      case "$cmdline" in
        *roslaunch*|*start-kuavo5w-mujoco.sh*)
          echo 0
          exit 0
          ;;
      esac
    fi
  fi
fi
rm -f /tmp/kuavo5w_mujoco.pid
echo 1
'@
if (($launchRunning | Select-Object -Last 1).Trim() -ne "0") {
    Write-Host "Starting MuJoCo launch in container background..."
    $visualizeArg = if ($VisualizeHumanoid) { "true" } else { "false" }
    $launchCommand = @"
cd /root/kuavo_ws
source /root/kuavo_ws/installed/setup.bash
source /root/kuavo_ws/devel/setup.bash
export LD_LIBRARY_PATH="/opt/drake/lib:/usr/lib:${LD_LIBRARY_PATH:-}"
export ROBOT_VERSION='$RobotVersion'
export DISABLE_ROS1_EOL_WARNINGS=1
export KUAVO_LAUNCH='$Launch'
export KUAVO_LAUNCH_ARGS='output_system_info:=false robot_type:=2 rviz:=false visualize_humanoid:=$visualizeArg'
nohup bash /root/kuavo_deploy/scripts/container/start-kuavo5w-mujoco.sh > /tmp/kuavo5w_mujoco_start.log 2>&1 &
echo `$! > /tmp/kuavo5w_mujoco.pid
cat /tmp/kuavo5w_mujoco.pid
"@
    Invoke-ContainerScript -Script $launchCommand -RemotePath "/tmp/kuavo_platform_launch.sh" | Out-Host
}
else {
    Write-Host "MuJoCo launch already appears to be running."
}

Write-Host "Waiting for ROS interfaces..."
$waitTemplate = @'
set -e
source /root/kuavo_ws/installed/setup.bash
source /root/kuavo_ws/devel/setup.bash
export LD_LIBRARY_PATH="/opt/drake/lib:/usr/lib:${LD_LIBRARY_PATH:-}"
for _i in $(seq 1 __LOOPS__); do
  if rostopic info /cmd_vel >/dev/null 2>&1 && rosservice info /mobile_manipulator_mpc_control >/dev/null 2>&1; then
    echo ready
    exit 0
  fi
  sleep 2
done
echo timeout
exit 1
'@
$waitLoops = [Math]::Max(1, [Math]::Ceiling($ReadyTimeoutSeconds / 2.0))
$waitScript = $waitTemplate.Replace("__LOOPS__", [string]$waitLoops)
$ready = Invoke-ContainerScript -Script $waitScript -RemotePath "/tmp/kuavo_platform_wait.sh"
$readyLast = ($ready | Select-Object -Last 1)
if ($null -eq $readyLast -or $readyLast.Trim() -ne "ready") {
    Write-Warning "ROS interfaces were not ready within $ReadyTimeoutSeconds seconds."
    Write-Host "Check logs:"
    Write-Host "  wsl -d $Distro -- docker exec -it $Container bash -lc 'tail -120 /tmp/kuavo5w_mujoco_start.log'"
    exit 1
}

Write-Host "ROS interfaces are ready."

if ($RunProbe -and [string]::IsNullOrWhiteSpace($Demo)) {
    $Demo = "probe"
}

if (-not [string]::IsNullOrWhiteSpace($Scenario)) {
    Write-Host "Running scenario: $Scenario"
    Invoke-ContainerScript -RemotePath "/tmp/kuavo_platform_run_scenario.sh" -Script @"
set -e
source /root/kuavo_ws/installed/setup.bash
source /root/kuavo_ws/devel/setup.bash
export LD_LIBRARY_PATH="/opt/drake/lib:/usr/lib:${LD_LIBRARY_PATH:-}"
export PYTHONPATH="/root/kuavo_ws/src/kuavo_humanoid_sdk:/root/kuavo_ws/devel/lib/python3/dist-packages:/root/kuavo_ws/installed/lib/python3/dist-packages:/opt/ros/noetic/lib/python3/dist-packages"
cd /root/kuavo_deploy
python3 -m kuavo_sim_platform.kuavo_sim.scenario '$Scenario'
"@
    exit $LASTEXITCODE
}

if (-not [string]::IsNullOrWhiteSpace($Script)) {
    Write-Host "Running imported script: $Script"
    Invoke-ContainerScript -RemotePath "/tmp/kuavo_platform_run_script.sh" -Script @"
set -e
source /root/kuavo_ws/installed/setup.bash
source /root/kuavo_ws/devel/setup.bash
export LD_LIBRARY_PATH="/opt/drake/lib:/usr/lib:${LD_LIBRARY_PATH:-}"
export PYTHONPATH="/root/kuavo_ws/src/kuavo_humanoid_sdk:/root/kuavo_ws/devel/lib/python3/dist-packages:/root/kuavo_ws/installed/lib/python3/dist-packages:/opt/ros/noetic/lib/python3/dist-packages"
cd /root/kuavo_deploy
python3 '$Script'
"@
    exit $LASTEXITCODE
}

if (-not [string]::IsNullOrWhiteSpace($Demo)) {
    $script = switch ($Demo) {
        "probe" { "kuavo_sim_platform/scripts/demo_base_probe.py" }
        "forward" { "kuavo_sim_platform/scripts/demo_base_forward.py" }
        "stop" { "kuavo_sim_platform/scripts/demo_stop.py" }
        default { throw "Unknown demo: $Demo" }
    }
    Write-Host "Running demo: $Demo"
    Invoke-ContainerScript -RemotePath "/tmp/kuavo_platform_run_demo.sh" -Script @"
set -e
source /root/kuavo_ws/installed/setup.bash
source /root/kuavo_ws/devel/setup.bash
export LD_LIBRARY_PATH="/opt/drake/lib:/usr/lib:${LD_LIBRARY_PATH:-}"
export PYTHONPATH="/root/kuavo_ws/src/kuavo_humanoid_sdk:/root/kuavo_ws/devel/lib/python3/dist-packages:/root/kuavo_ws/installed/lib/python3/dist-packages:/opt/ros/noetic/lib/python3/dist-packages"
cd /root/kuavo_deploy
python3 '$script'
"@
    exit $LASTEXITCODE
}

Write-Host "Simulator is running and script platform is connected."
Write-Host "Run a safe probe with:"
Write-Host "  powershell -NoProfile -ExecutionPolicy Bypass -File scripts/windows/start-kuavo5w-platform.ps1 -RunProbe"
Write-Host "Attach to container with:"
Write-Host "  wsl -d $Distro -- docker exec -it $Container bash"
Write-Host "View launch log with:"
Write-Host "  wsl -d $Distro -- docker exec -it $Container bash -lc 'tail -120 /tmp/kuavo5w_mujoco_start.log'"
