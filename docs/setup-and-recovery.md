# Kuavo 5-W Setup and Recovery

This document keeps setup, recovery, and release checks in one place. Daily operation should still start from the Web console.

## Environment Baseline

Known baseline values used by the current scripts:

- Windows project path: `E:\project\kuavo`
- WSL distro: `Ubuntu-20.04`
- WSL project path: `/mnt/e/project/kuavo`
- container: `kuavo5w_sim`
- image: `kuavo-ros-opensource:master`
- robot version: `62`
- default launch: `load_kuavo_mujoco_sim_wheel.launch`
- deploy mount inside container: `/root/kuavo_deploy`

## Setup Flow

1. Install WSL2 and Ubuntu.
2. Install Docker Desktop and enable WSL integration.
3. Clone or prepare the Kuavo source under `/home/bamboo/kuavo_ws_src/kuavo-ros-opensource`.
4. Build or import the Docker image.
5. Start the Web console with `scripts\windows\start-kuavo5w-web-control.ps1`.
6. Use the Web console to start/connect GUI simulation and check readiness.

Lower-level scripts under `scripts/wsl/` and `scripts/container/` remain available for image/container setup and debugging.

## Recovery Flow

Start with the least destructive option:

1. In the Web console, run `查看 MuJoCo 日志` and `检查 ROS 接口`.
2. If motion control is unsafe, run `复原 / 停止`.
3. If MPC is paused or stuck, use `暂停 MPC` / `恢复 MPC` deliberately.
4. If ROS launch is wedged, use `停止仿真进程`, then start GUI simulation again.
5. From another PowerShell, emergency restore remains available:

```powershell
cd E:\project\kuavo
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\windows\kuavo5w-restore.ps1
```

Avoid rebuilding images, deleting containers, or restarting WSL until logs and interface checks have been captured.

## Diagnostics

The Web console exposes:

- MuJoCo launch log tail;
- ROS interface inspection;
- SSH monitor;
- read-only smoke test;
- environment snapshot collection.

Environment snapshots are generated under `docs/env_snapshots/` and are treated as runtime artifacts, not primary documentation.

## Release/Hand-Off Checks

Before hand-off:

```powershell
python -m py_compile kuavo_sim_platform\web_control\server.py scripts\smoke_test.py scripts\collect_env_snapshot.py
python -m unittest discover -s kuavo_sim_platform\tests
```

Then run Web diagnostics if the simulator is available. Record failures with command output, timestamp, and whether GUI was visible.

## Archived Detail

Historical long-form documents were moved to `docs/archive/` for reference. Prefer the current README, operator guide, developer guide, and setup/recovery guide for active workflow decisions.
