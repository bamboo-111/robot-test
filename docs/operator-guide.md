# Kuavo 5-W Operator Guide

Use the Web console for daily operation. It keeps startup, experiments, diagnostics, and recovery in one place so operators do not need to choose between overlapping scripts.

## 1. Start the Web Console

Run from Windows PowerShell:

```powershell
cd E:\project\kuavo
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\windows\start-kuavo5w-web-control.ps1 -Port 8765
```

Open `http://127.0.0.1:8765/`.

## 2. Prepare the Simulator

In the Web console, use `启动 / 连接 GUI 仿真` for motion experiments. This starts or reuses the container and launches MuJoCo/ROS with `visualize_humanoid:=true`.

Use `检查 ROS Ready` after startup to confirm `/cmd_vel` and `/mobile_manipulator_mpc_control` are available.

`后台接口检查` only checks whether ROS/service interfaces can be reached. It is useful before diagnostics or remote script preflight, but it cannot prove a gesture or base motion looked correct.

## 3. Run Experiments

Recommended order:

1. Run `安全探测` first.
2. Run `前进 Demo` only after the probe behaves as expected.
3. Run a YAML scenario from the scenario selector.
4. Import and run Python scripts only after confirming no other operator is controlling the simulator.

Imported scripts are shown with category metadata:

- `experiment`: visible action scripts for GUI-backed experiments.
- `diagnostic`: read-only or targeted diagnostic scripts.
- `import-test`: hidden from the normal list because they only test upload/runtime plumbing.

## 4. Observe and Diagnose

Use the Web console diagnostic group:

- `查看 MuJoCo 日志`: tails `/tmp/kuavo5w_mujoco_start.log`.
- `检查 ROS 接口`: runs the curated interface inspector inside the container.
- `运行 Smoke Test`: runs read-only host checks.
- `采集环境快照`: writes a timestamped snapshot under `docs/env_snapshots/`.
- `SSH 实时监控`: opens the read-only SSH status page.

## 5. Safe Control

Use `暂停 MPC` and `恢复 MPC` only when coordinating with other operators.

Use `复原 / 停止` to publish zero base velocity and switch to `NoControl`.

Use `停止仿真进程` only when the simulator needs to stop. It kills ROS launch/master processes and removes the MuJoCo pid file, so it is intentionally placed in the safety group.

## 6. Command-Line Fallbacks

- `scripts/windows/start-kuavo5w-web-control.ps1`: recommended daily entry.
- `scripts/windows/kuavo5w-restore.ps1`: emergency restore from another PowerShell.
- `scripts/windows/kuavo5w-script-menu.ps1`: no-browser fallback only.
- `scripts/windows/start-web.ps1` and `scripts/windows/start-sim.ps1`: compatibility wrappers.
- `scripts/windows/start-kuavo5w-mujoco.ps1`: legacy foreground roslaunch debugging only.
