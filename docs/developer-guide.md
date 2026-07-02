# Kuavo 5-W Developer Guide

This guide covers the project-side Python wrapper, YAML scenarios, and imported Web scripts.

## Python Wrapper

The package lives in `kuavo_sim_platform/kuavo_sim/` and exposes `KuavoSim` for ROS-backed control. It wraps base velocity, mode switching, arm joints, head/body pose, hands, torso, lower body, IK/FK helpers, and reach-time state monitors.

Typical runtime scripts should run inside the sourced Kuavo container through the Web console or platform script. Offline checks can run on the host when they do not import ROS packages.

## YAML Scenarios

YAML scenarios live in `kuavo_sim_platform/scenarios/` and are run by `kuavo_sim_platform.kuavo_sim.scenario`.

Supported actions include:

- readiness and mode: `wait_ready`, `set_mode`, `set_quick_mode`, `set_arm_control_mode`;
- base: `cmd_vel`, `cmd_vel_world`, `move_for`, `move_world_for`, `cmd_pose`, `cmd_pose_world`, `stop_base`;
- upper/lower body: `arm_joint`, `two_arm_hand_pose`, `leg_joint`, `torso_pose`, `head_body_pose`, `hand_position`;
- timing: `sleep`.

Keep first-run scenarios small and observable in the GUI.

## Imported Scripts

Web-imported scripts live in `kuavo_sim_platform/imported_scripts/` after upload. The Web API accepts only ASCII `.py` filenames and limits uploads to 512 KiB.

Script list categories are defined in `kuavo_sim_platform/web_control/server.py`:

- `experiment`: shown as a normal runnable action.
- `diagnostic`: shown, but expected to be read-only or narrowly diagnostic.
- `import-test`: hidden from the normal list.

Rules for imported scripts:

- no unbounded loops;
- include explicit sleeps or bounded waits for repeated publishing;
- call safe stop or rely on `KuavoSim` context cleanup on exit;
- do not publish base motion unless the operator is watching the GUI;
- use angle-scale arm values consistently with current Kuavo 5-W examples.

## Checks

Run before handing off changes:

```powershell
python -m py_compile kuavo_sim_platform\web_control\server.py scripts\smoke_test.py scripts\collect_env_snapshot.py
python -m py_compile kuavo_sim_platform\kuavo_sim\*.py kuavo_sim_platform\scripts\*.py
python -m unittest discover -s kuavo_sim_platform\tests
```

If the container is running, use the Web console diagnostics for ROS interface checks, smoke tests, and logs.
