# Kuavo 5-W Windows Docker Simulation Setup

This guide sets up Kuavo 5-W simulation on a Windows host by running the Linux ROS stack inside Docker. Windows is used only for WSL, Docker Desktop, GUI display, and file editing.

Target architecture:

```text
Windows 11
  -> WSL2 Ubuntu 20.04/22.04
    -> Docker Desktop WSL2 backend
      -> Kuavo ROS Docker container
        -> Gazebo / MuJoCo / RViz through WSLg
```

Do not install Kuavo, ROS, Gazebo, or MuJoCo natively on Windows. Do not compile Kuavo under `/mnt/c`; keep the repository in the WSL ext4 filesystem, for example `~/kuavo_ws_src`.

## 1. Install WSL2 and Ubuntu

Run in Windows PowerShell as Administrator:

```powershell
wsl --install -d Ubuntu-22.04
wsl --update
wsl -l -v
```

Ubuntu 22.04 is the default recommendation. Ubuntu 20.04 is also acceptable if required by the Kuavo branch or image you use.

## 2. Install Docker Desktop

Docker Desktop is required and is not installed by these scripts.

1. Install Docker Desktop for Windows from the official Docker website.
2. Open Docker Desktop.
3. Enable `Settings > General > Use the WSL 2 based engine`.
4. Enable `Settings > Resources > WSL Integration > Ubuntu-22.04` or your target Ubuntu distro.
5. Ensure Docker Desktop is using Linux containers, not Windows containers.

Then verify from Windows PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/windows/check-env.ps1
```

The check script should report Docker as `linux / ...`. If Docker is missing, it will print installation guidance. If the daemon is unreachable, start Docker Desktop and retry.

## 3. Clone Kuavo master in WSL

Open WSL Ubuntu and run:

```bash
bash scripts/wsl/clone-kuavo.sh
cd ~/kuavo_ws_src/kuavo-ros-opensource
```

Defaults:

```bash
KUAVO_REPO_URL=https://gitcode.com/OpenLET/kuavo-ros-opensource.git
KUAVO_BRANCH=master
KUAVO_WORKDIR=~/kuavo_ws_src
```

The script prints the actual `docker/` content and the first matching `*sim*.launch` files so later steps can adapt to the current `master` branch.

## 4. Build or import the Docker image

Preferred path, build locally:

```bash
cd ~/kuavo_ws_src/kuavo-ros-opensource
docker build -t kuavo-ros-opensource:master -f docker/Dockerfile docker
```

The official Dockerfile copies helper files such as `config_ccache.sh` from the `docker/` directory, so the build context must be `docker`, not the repository root. If the official Dockerfile path changes, inspect the printed `docker/` content and adjust `-f`.

For unstable networks, prefer the retry wrapper from this deployment repo:

```bash
cd /mnt/e/project/kuavo
BUILD_TIMEOUT_SECONDS=900 BUILD_RETRY_ATTEMPTS=20 BUILD_RETRY_SLEEP_SECONDS=20 bash scripts/wsl/build-kuavo-image-retry.sh
```

The wrapper kills a hung build attempt, waits briefly, and retries. Docker reuses all successful cached layers, so retries usually continue near the last completed layer.

Alternative path, import a prebuilt official image:

```bash
docker load -i kuavo_opensource_mpc_wbc_img_v1.3.0.tar.gz
docker images
export KUAVO_IMAGE=<actual-image-name:tag>
```

Do not hardcode a prebuilt image name as the only supported path. Use `KUAVO_IMAGE` when the real image name differs.

## 5. Start the Windows GUI container

From WSL Ubuntu:

```bash
export ROBOT_VERSION=62
export KUAVO_IMAGE=kuavo-ros-opensource:master
bash scripts/wsl/run-kuavo-container-windows-gui.sh
```

The launcher:

- checks that Docker is reachable from WSL
- mounts the repository to `/root/kuavo_ws`
- mounts these deployment scripts read-only to `/root/kuavo_deploy`
- passes WSLg variables for X11, Wayland, and audio
- mounts `/tmp/.X11-unix`, `/mnt/wslg`, and `/dev`
- enables WSLg vGPU when `/dev/dxg` exists

If `docker/run.sh` exists in the Kuavo repository, compare its mounts and device options with this launcher before hardware-oriented work. This Windows GUI launcher is a deployment helper, not a replacement for all future robot-specific mount logic.

## 6. Build Kuavo inside the container

Inside the container:

```bash
bash /root/kuavo_deploy/scripts/container/build-kuavo.sh
```

Defaults:

```bash
ROBOT_VERSION=62
CLEAN_BUILD=0
EXTRA_PKGS=
```

For the current `master` wheel launch path, use a wheel-supported robot version. The repository currently includes wheel interface task configs for `kuavo_s60` through `kuavo_s63`; using `ROBOT_VERSION=42` or `50` with `load_kuavo_mujoco_sim_wheel.launch` can fail with missing wheel/manipulator config fields.

To compile additional packages for Gazebo:

```bash
EXTRA_PKGS=gazebo_sim bash /root/kuavo_deploy/scripts/container/build-kuavo.sh
```

The build and launch scripts source `installed/setup.bash` before the workspace setup where needed so runtime libraries such as Drake/OpenVINO are present in `LD_LIBRARY_PATH`.

The build script follows the official build shape:

```bash
catkin config -DCMAKE_ASM_COMPILER=/usr/bin/as -DCMAKE_BUILD_TYPE=Release
source installed/setup.zsh
catkin build humanoid_controllers
```

It falls back to `installed/setup.bash` when needed.

## 7. Verify GUI forwarding

Inside the container:

```bash
bash /root/kuavo_deploy/scripts/container/test-gui.sh
```

Expected result: `xeyes`, `rviz`, or `gazebo` appears on the Windows desktop.

If `glxinfo -B` is available:

- renderer containing D3D12 or NVIDIA usually means vGPU is active
- renderer containing llvmpipe usually means software rendering

Install `mesa-utils` in the container only if you need OpenGL renderer verification.

## 8. Start MuJoCo or Gazebo simulation

MuJoCo:

```bash
bash /root/kuavo_deploy/scripts/container/start-kuavo5w-mujoco.sh
```

Gazebo:

```bash
bash /root/kuavo_deploy/scripts/container/start-kuavo5w-gazebo.sh
```

The scripts do not assume a wheel-specific launch exists. They search current `master` first, then fall back to:

```text
load_kuavo_mujoco_sim.launch
load_kuavo_gazebo_sim.launch
```

Override explicitly when the real 5-W launch is known:

```bash
KUAVO_LAUNCH=<real-launch-name>.launch bash /root/kuavo_deploy/scripts/container/start-kuavo5w-mujoco.sh
```

Specific 5-W assets, models, and dedicated launch names are intentionally left for a later adaptation step.

From Windows PowerShell, the one-command launcher is:

```powershell
cd E:\project\kuavo
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/windows/start-kuavo5w-mujoco.ps1
```

It starts or reuses the `kuavo5w_sim` container, mounts the Kuavo workspace and deployment scripts, then runs the MuJoCo wheel launch in the foreground. Use `-RecreateContainer` if the container environment needs to be recreated:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/windows/start-kuavo5w-mujoco.ps1 -RecreateContainer
```

For the script-control platform, use the full platform launcher. It starts or reuses the container, starts MuJoCo in the container background, waits for `/cmd_vel` and `/mobile_manipulator_mpc_control`, and then optionally runs a demo:

```powershell
cd E:\project\kuavo
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/windows/start-kuavo5w-platform.ps1
```

Safe first motion probe:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/windows/start-kuavo5w-platform.ps1 -RunProbe
```

Run a YAML scenario:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/windows/start-kuavo5w-platform.ps1 -Scenario kuavo_sim_platform/scenarios/base_probe.yaml
```

By default the helper scripts pass `output_system_info:=false robot_type:=2`. `output_system_info:=false` avoids repeated CPU temperature warnings inside WSL/Docker, where the `sensors` command usually cannot read host hardware sensors. `robot_type:=2` matches the working `ROBOT_VERSION=62` MuJoCo wheel runtime observed on current master. Override or add launch args with `KUAVO_LAUNCH_ARGS` when needed:

```bash
KUAVO_LAUNCH_ARGS="output_system_info:=false robot_type:=2 visualize_humanoid:=true" \
KUAVO_LAUNCH=load_kuavo_mujoco_sim_wheel.launch \
bash /root/kuavo_deploy/scripts/container/start-kuavo5w-mujoco.sh
```

## 9. Windows 10 fallback

Windows 11 with WSLg is the recommended path. On Windows 10, install VcXsrv or Xming and allow it through the firewall.

In WSL:

```bash
export DISPLAY=$(grep nameserver /etc/resolv.conf | awk '{print $2}'):0
export LIBGL_ALWAYS_INDIRECT=1
```

Then start the container with the same WSL launcher. Expect lower reliability for Gazebo, MuJoCo, and OpenGL than on Windows 11 with WSLg.

## Troubleshooting

Docker is not installed:

- Install Docker Desktop for Windows.
- Enable the WSL2 backend and Ubuntu integration.
- Re-run `scripts/windows/check-env.ps1`.

Docker daemon is unreachable:

- Start Docker Desktop.
- Wait until it reports running.
- Re-run `docker info` from PowerShell and WSL.

Docker reports Windows containers:

- Switch Docker Desktop to Linux containers.
- `docker info --format '{{.OSType}} / {{.OperatingSystem}}'` must begin with `linux`.

`DISPLAY` is empty or GUI does not show:

- Confirm this is a WSLg session on Windows 11.
- Check `ls /mnt/wslg` and `ls /tmp/.X11-unix`.
- Run `scripts/container/test-gui.sh` inside the container.

Gazebo is black or very slow:

- Confirm `/dev/dxg` exists in WSL.
- Confirm the container got `/usr/lib/wsl` and `LD_LIBRARY_PATH=/usr/lib/wsl/lib`.
- Check `glxinfo -B` if available.

Catkin build is slow:

- Ensure the repository is under `~/kuavo_ws_src`, not `/mnt/c`, `/mnt/d`, or another Windows-mounted path.

Launch file not found:

- Run `find src -name "*sim*.launch"` inside `/root/kuavo_ws`.
- Use `KUAVO_LAUNCH=<name>.launch` to override.
- Do not assume wheel-specific launch names exist on the current `master` branch.
