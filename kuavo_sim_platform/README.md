# Kuavo 5-W Script Control Platform v1

Minimal Python/YAML wrapper for the official Kuavo 5-W ROS1 control interfaces.

This v1 package intentionally covers only the base velocity path and mode
switching. It does not drive the joystick terminal, modify MuJoCo internals, or
change Kuavo controller source code.

## Status

This repository-side implementation has only passed offline checks. Runtime ROS
interfaces still need to be verified inside the container before running motion
demos.

## Verified Runtime Interfaces

Fill this table after running `rostopic info`, `rosservice info`, and
`rossrv show` inside the sourced Kuavo container.

| Item | Runtime result |
|---|---|
| `/cmd_vel` | TODO, expected `geometry_msgs/Twist` |
| `/cmd_vel_world` | TODO, expected `geometry_msgs/Twist` |
| `/cmd_pose` | TODO |
| `/cmd_pose_world` | TODO |
| `/mobile_manipulator_mpc_control` | TODO |
| `lb_ctrl_api.py` | TODO, expected `set_control_mode(int)` |
| mode feedback | TODO, assumed `std_msgs/Int32` for v1 |
| reach time feedback | TODO |

## Runtime Setup

Start the known working simulation with `ROBOT_VERSION=62`.

```bash
wsl -d Ubuntu-20.04
cd /mnt/e/project/kuavo
export ROBOT_VERSION=62
export KUAVO_IMAGE=kuavo-ros-opensource:master
bash scripts/wsl/run-kuavo-container-windows-gui.sh
```

Inside the container:

```bash
source /root/kuavo_ws/devel/setup.bash
export ROBOT_VERSION=62
export DISABLE_ROS1_EOL_WARNINGS=1
KUAVO_LAUNCH=load_kuavo_mujoco_sim_wheel.launch \
  bash /root/kuavo_deploy/scripts/container/start-kuavo5w-mujoco.sh
```

## First Motion Probe

Run the probe before any faster movement:

```bash
cd /mnt/e/project/kuavo
python3 kuavo_sim_platform/scripts/demo_base_probe.py
```

The probe uses `x=0.05` and `duration=1.0`. If the robot moves in the opposite
direction, stop and record the actual convention before changing wrapper logic.

## YAML Scenario

```bash
cd /mnt/e/project/kuavo
python3 -m kuavo_sim_platform.kuavo_sim.scenario \
  kuavo_sim_platform/scenarios/base_probe.yaml
```

## Offline Checks

```bash
cd /mnt/e/project/kuavo
python -m py_compile kuavo_sim_platform/kuavo_sim/*.py \
  kuavo_sim_platform/scripts/*.py
python -m unittest discover -s kuavo_sim_platform/tests
```

If `pytest` is available:

```bash
python -m pytest kuavo_sim_platform/tests
```

## Safety Defaults

- `move_for()` always publishes zero velocity after the timed motion.
- Default limits are `max_vx=0.30`, `max_vy=0.30`, `max_wyaw=0.50`.
- `KuavoSim` context manager tries `stop_base()` and `NoControl` on exit.
- Mode switching uses official `lb_ctrl_api.set_control_mode(int)` when found.
- Direct service fallback is intentionally blocked until the actual service
  type and fields are verified in the container.
