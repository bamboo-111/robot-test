# Kuavo 5-W Control Workspace

This workspace is organized around one daily workflow: start the local Web console, run GUI-backed simulation experiments from the browser, and keep command-line scripts as lower-level support tools.

## Daily Entry

Run from Windows PowerShell:

```powershell
cd E:\project\kuavo
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\windows\start-kuavo5w-web-control.ps1 -Port 8765
```

Open:

```text
http://127.0.0.1:8765/
```

The Web console is the recommended place to:

- start or connect the GUI simulation;
- check ROS readiness;
- run the safe probe, demos, YAML scenarios, and imported scripts;
- view MuJoCo logs, SSH status, ROS interface checks, smoke tests, and environment snapshots;
- pause/resume MPC, restore to a safe state, or stop simulator processes.

## GUI vs Background Checks

Motion experiments should use the GUI simulation entry. Without a visible simulator, arm gestures, base movement, and combined actions cannot be judged reliably; only ROS topics, services, logs, and exit codes can be checked.

The Web console still provides a background interface check mode for quick ROS/service validation, but it is not a replacement for GUI experiment verification.

## Directory Map

- `kuavo_sim_platform/web_control/`: Web console and local API server.
- `kuavo_sim_platform/kuavo_sim/`: Python wrapper for Kuavo ROS control interfaces.
- `kuavo_sim_platform/scenarios/`: YAML scenarios runnable from the Web console.
- `kuavo_sim_platform/imported_scripts/`: imported or curated Web-run scripts, grouped by experiment/diagnostic/import-test metadata.
- `scripts/windows/`: Windows entry scripts. Prefer `start-kuavo5w-web-control.ps1`.
- `scripts/container/` and `scripts/wsl/`: lower-level container, WSL, and image support scripts.
- `docs/`: current operator, developer, setup, and recovery documents.
- `docs/archive/`: historical long-form notes retained for reference.

## Current Docs

- `docs/operator-guide.md`: daily Web-console operation.
- `docs/developer-guide.md`: SDK, YAML scenarios, imported-script rules, and safety constraints.
- `docs/setup-and-recovery.md`: Windows/WSL/Docker setup, recovery, smoke tests, and environment snapshots.
