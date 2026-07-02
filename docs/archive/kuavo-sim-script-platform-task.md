# Kuavo 5-W Script Control Platform - Next Task Brief

## 1. Current State

Kuavo 5-W MuJoCo wheel simulation is already running successfully on Windows through WSL2, Docker Desktop, and WSLg.

Working paths:

- Deployment helper repo on Windows/WSL mount: `/mnt/e/project/kuavo`
- Kuavo source repo in WSL ext4: `~/kuavo_ws_src/kuavo-ros-opensource`
- Kuavo workspace inside container: `/root/kuavo_ws`
- Deployment helper scripts inside container: `/root/kuavo_deploy`

Known working container startup:

```bash
wsl -d Ubuntu-20.04
cd /mnt/e/project/kuavo
export ROBOT_VERSION=62
export KUAVO_IMAGE=kuavo-ros-opensource:master
bash scripts/wsl/run-kuavo-container-windows-gui.sh
```

Known working MuJoCo 5-W launch inside the container:

```bash
export ROBOT_VERSION=62
export DISABLE_ROS1_EOL_WARNINGS=1
KUAVO_LAUNCH=load_kuavo_mujoco_sim_wheel.launch \
bash /root/kuavo_deploy/scripts/container/start-kuavo5w-mujoco.sh
```

Important runtime notes:

- Use `ROBOT_VERSION=62`. Current master has wheel task configs for `kuavo_s60` to `kuavo_s63`; `42` and `50` caused runtime config mismatch.
- The helper launch script defaults to `output_system_info:=false` to suppress container CPU temperature warning spam.
- MuJoCo, RViz, and the joystick simulator Terminal already display through WSLg.
- Manual keyboard control only works when focus is on the white joystick simulator Terminal, but the new platform must not depend on key focus or manual keypresses.

## 2. Correct Direction

The next task is not to reverse engineer keyboard control. Official documentation already defines the 5-W control APIs.

Build a script platform as a wrapper around the official ROS1 5-W interfaces:

```text
Python/YAML scenario
  -> Kuavo 5-W Python SDK wrapper
    -> official ROS topics/services
      -> running Kuavo MuJoCo wheel simulation
```

Do not control the simulator by sending keys to the joystick Terminal. Do not modify MuJoCo internals or Kuavo controller source for v1 unless a minimal compatibility fix is unavoidable.

Official docs to read first:

- Product introduction: `https://kuavo.lejurobot.com/beta_manual/basic_usage/kuavo-ros-control/docs/1产品介绍/产品介绍/`
- ROS1 SDK introduction: `https://kuavo.lejurobot.com/beta_manual/basic_usage/kuavo-ros-control/docs/4开发接口/SDK介绍/`
- Kuavo 5-W interface usage: `https://kuavo.lejurobot.com/beta_manual/basic_usage/kuavo-ros-control/docs/4开发接口/Kuavo 5-W 接口使用文档/`

Local examples and SDK directories to inspect before implementation:

```text
/root/kuavo_ws/src/demo/test_kuavo_wheel_real
/root/kuavo_ws/src/kuavo_sdk
/root/kuavo_ws/src/kuavo_humanoid_sdk
/root/kuavo_ws/src/kuavo_humanoid_websocket_sdk
```

## 3. Official 5-W Interfaces To Wrap

Use these interfaces as the v1 platform surface. Verify exact message/service definitions locally with `rostopic info`, `rosmsg show`, `rosservice info`, and `rossrv show` before coding.

### Base Velocity Control

Topic:

```text
/cmd_vel
```

Purpose:

- Robot-body-frame chassis velocity control.
- Use for basic scripted movement such as forward/backward/lateral/yaw.
- Official behavior: if command publishing stops for about 1 second, or if zero velocity is published, the robot stops.
- This should be the default v1 movement interface.

Expected message:

```text
geometry_msgs/Twist
```

Wrapper methods:

```python
bot.cmd_vel(x=0.2, y=0.0, yaw=0.0)
bot.move_for(duration=2.0, x=0.2, y=0.0, yaw=0.0, rate=20)
bot.stop_base()
```

### World-Frame Base Velocity Control

Topic:

```text
/cmd_vel_world
```

Purpose:

- World-frame chassis velocity control.
- Use only when scenario logic needs global-frame movement.

Expected message:

```text
geometry_msgs/Twist
```

Wrapper methods:

```python
bot.cmd_vel_world(x=0.2, y=0.0, yaw=0.0)
bot.move_world_for(duration=2.0, x=0.2, y=0.0, yaw=0.0, rate=20)
```

### Base Pose Control

Topics:

```text
/cmd_pose
/cmd_pose_world
```

Purpose:

- Command relative/body-frame or world-frame base pose targets.
- Use for scenario steps such as "move to pose" after velocity control is stable.

Local verification required:

```bash
rostopic info /cmd_pose
rostopic info /cmd_pose_world
rosmsg show <message-type>
```

Wrapper methods:

```python
bot.cmd_pose(...)
bot.cmd_pose_world(...)
bot.wait_pose_reached(timeout=10)
```

### Lower-Body / Torso Control

Topics:

```text
/lb_leg_traj
/cmd_lb_torso_pose
```

Purpose:

- Lower-body leg trajectory and torso pose control.
- Keep out of the first movement demo unless official examples show the exact required message fields.

Local verification required:

```bash
rostopic info /lb_leg_traj
rostopic info /cmd_lb_torso_pose
rosmsg show <message-type>
```

### Arm Joint Control

Topic:

```text
/kuavo_arm_traj
```

Purpose:

- Arm joint trajectory command.
- Use after base movement v1 is stable.

Expected v1 wrapper:

```python
bot.arm_joint(joints=[...], duration=...)
bot.wait_arm_joint_reached(timeout=10)
```

### Arm End-Effector Control

Topic:

```text
/mm/two_arm_hand_pose_cmd
```

Purpose:

- Two-arm hand/end-effector pose command for mobile manipulation.

Expected v1 wrapper:

```python
bot.two_arm_hand_pose(...)
bot.wait_arm_ee_reached(timeout=10)
```

### Main MPC Control Mode Service

Service:

```text
/mobile_manipulator_mpc_control
```

Official service type:

```text
kuavo_msgs/changeTorsoCtrlMode
```

Control mode values:

```text
0 = NoControl
1 = ArmOnly
2 = BaseOnly
3 = BaseArm
4 = ArmEeOnly
```

Wrapper methods:

```python
bot.set_mode(0)
bot.set_mode_no_control()
bot.set_mode_arm_only()
bot.set_mode_base_only()
bot.set_mode_base_arm()
bot.set_mode_arm_ee_only()
```

Implementation requirements:

- Wait for service before calling.
- Validate mode is one of `0..4`.
- Confirm mode change using `/mobile_manipulator/lb_mpc_control_mode` if available.

### Quick Mode Service

Service:

```text
/enable_lb_arm_quick_mode
```

Purpose:

- Enable/disable quick lower-body/arm mode according to official 5-W behavior.

Wrapper method:

```python
bot.enable_quick_mode(True)
bot.enable_quick_mode(False)
```

Local verification required:

```bash
rosservice info /enable_lb_arm_quick_mode
rossrv show <service-type>
```

## 4. Feedback / Readiness Interfaces

Use feedback topics to avoid blind sleeps where possible.

Official feedback topics to verify and wrap:

```text
/mobile_manipulator/lb_mpc_control_mode
/mobile_manipulator_mpc_observation
/mobile_manipulator_wbc_observation
/lb_cmd_pose_reach_time
/lb_arm_joint_reach_time
/lb_arm_ee_reach_time
```

Expected SDK methods:

```python
bot.wait_ros(timeout=30)
bot.wait_sim_ready(timeout=30)
bot.wait_mode(mode=2, timeout=5)
bot.wait_pose_reached(timeout=10)
bot.wait_arm_joint_reached(timeout=10)
bot.wait_arm_ee_reached(timeout=10)
bot.get_observation()
```

Minimum readiness rule for v1:

- ROS master is reachable.
- `/mobile_manipulator_mpc_control` is available.
- `/cmd_vel` publisher can be created.
- `/mobile_manipulator/lb_mpc_control_mode` is receiving or queryable.
- Robot has been switched to `BaseOnly` or `BaseArm` before base velocity commands are sent.

## 5. V1 Deliverable

Create a small script-control package in this deployment repo, not in the Kuavo source repo unless there is a strong reason.

Proposed structure:

```text
kuavo_sim_platform/
  kuavo_sim/
    __init__.py
    client.py
    modes.py
    base.py
    arm.py
    state.py
    scenario.py
  scripts/
    demo_base_forward.py
    demo_base_square.py
    demo_stop.py
  scenarios/
    base_forward.yaml
    base_square.yaml
  README.md
```

Minimum Python API:

```python
from kuavo_sim import KuavoSim

bot = KuavoSim()
bot.wait_ready(timeout=30)
bot.set_mode_base_only()
bot.move_for(duration=2.0, x=0.2, y=0.0, yaw=0.0)
bot.stop_base()
bot.set_mode_no_control()
```

The first demo must not use `/joy` or keyboard simulation. It should use `/mobile_manipulator_mpc_control` plus `/cmd_vel`.

## 6. YAML Scenario Runner

After the direct Python demo works, add a simple YAML runner.

Example scenario:

```yaml
name: base_forward
steps:
  - action: wait_ready
    timeout: 30
  - action: set_mode
    mode: BaseOnly
  - action: move_for
    duration: 2.0
    x: 0.2
    y: 0.0
    yaw: 0.0
  - action: stop_base
  - action: set_mode
    mode: NoControl
```

Target command:

```bash
python3 -m kuavo_sim.scenario kuavo_sim_platform/scenarios/base_forward.yaml
```

## 7. Validation Commands

Run inside the container after launching MuJoCo:

```bash
source /root/kuavo_ws/devel/setup.bash
rostopic list
rosservice list
rostopic info /cmd_vel
rostopic info /cmd_vel_world
rostopic info /cmd_pose
rostopic info /cmd_pose_world
rostopic info /kuavo_arm_traj
rostopic info /mm/two_arm_hand_pose_cmd
rosservice info /mobile_manipulator_mpc_control
rossrv show kuavo_msgs/changeTorsoCtrlMode
rostopic echo -n 1 /mobile_manipulator/lb_mpc_control_mode
```

Also inspect local official examples:

```bash
find /root/kuavo_ws/src/demo/test_kuavo_wheel_real -maxdepth 4 -type f | sort
grep -R -n "mobile_manipulator_mpc_control\|cmd_vel\|cmd_vel_world\|cmd_pose\|kuavo_arm_traj\|two_arm_hand_pose_cmd" \
  /root/kuavo_ws/src/demo/test_kuavo_wheel_real \
  /root/kuavo_ws/src/kuavo_sdk \
  /root/kuavo_ws/src/kuavo_humanoid_sdk
```

## 8. Acceptance Criteria

The task is complete when:

- A Python demo switches to `BaseOnly`, publishes `/cmd_vel`, moves the wheel robot briefly, stops, and returns to `NoControl`.
- The demo works while MuJoCo/RViz are open and does not require keyboard focus.
- The SDK wraps `/mobile_manipulator_mpc_control` with named mode helpers.
- The SDK has safe timeout behavior for missing ROS master, missing service, missing topic, or mode change failure.
- A YAML scenario can run the same base-forward behavior.
- Documentation lists all official 5-W interfaces used by the platform.

## 9. Pitfalls To Avoid

- Do not build the new platform around joystick keypresses or `/joy` unless explicitly implementing a compatibility fallback.
- Do not use `ROBOT_VERSION=42` or `50` for wheel MuJoCo on current master; use `62`.
- Do not press movement keys in the MuJoCo window; manual control only belongs to the joystick simulator Terminal.
- Do not treat `system_info_publisher` CPU temperature warnings as failures.
- Do not source `setup.zsh` from bash scripts; use `setup.bash` under bash.
- Do not write into build/devel/log/output directories as part of the platform.
- Keep Kuavo source under WSL ext4, not `/mnt/c`.

## 10. First Implementation Order

1. Start the known working MuJoCo simulation with `ROBOT_VERSION=62`.
2. Verify exact message/service types for the official interfaces with `rostopic`, `rosmsg`, `rosservice`, and `rossrv`.
3. Read `src/demo/test_kuavo_wheel_real` and SDK examples.
4. Implement `KuavoSim.wait_ready`, `set_mode_*`, `cmd_vel`, `move_for`, and `stop_base`.
5. Run `demo_base_forward.py`.
6. Add YAML scenario runner only after the direct Python demo succeeds.

