# Kuavo 5-W Script Control Platform - 可执行落地计划 v1

本文档的目标不是一次性贴出所有源码,而是把 Kuavo 5-W 脚本控制平台拆成可执行、可验证、可回滚的实现步骤。每一步都有输入、产出、命令和验收标准,避免在 ROS 消息/服务未确认前写死错误假设。

## 0. 当前前提

已知仿真启动路径:

```bash
wsl -d Ubuntu-20.04
cd /mnt/e/project/kuavo
export ROBOT_VERSION=62
export KUAVO_IMAGE=kuavo-ros-opensource:master
bash scripts/wsl/run-kuavo-container-windows-gui.sh
```

容器内启动 5-W MuJoCo:

```bash
export ROBOT_VERSION=62
export DISABLE_ROS1_EOL_WARNINGS=1
KUAVO_LAUNCH=load_kuavo_mujoco_sim_wheel.launch \
  bash /root/kuavo_deploy/scripts/container/start-kuavo5w-mujoco.sh
```

必须遵守:

- 使用 `ROBOT_VERSION=62`; 当前 master 的轮式配置覆盖 `kuavo_s60` 到 `kuavo_s63`。
- v1 不做键盘模拟,不依赖 joystick terminal 焦点。
- v1 不改 MuJoCo、控制器源码或历史产物目录,除非后续明确确认是兼容性缺陷。
- 所有 ROS 类型、服务字段先在容器内确认,再写代码。

## 1. 最小可交付目标

v1 只交付一条稳定闭环:

```text
Python/YAML scenario
  -> kuavo_sim.KuavoSim
    -> official ROS1 topics/services
      -> running Kuavo 5-W MuJoCo simulation
```

最小演示:

1. 连接已有 ROS master。
2. 等待 MPC 与底盘命令订阅者就绪。
3. 切换 `BaseOnly` 模式并确认生效。
4. 以很小速度前进 1 秒,发布零速并保持。
5. 切回 `NoControl`。
6. 同一动作可由 Python demo 和 YAML scenario 两种方式触发。
7. 任一步失败时自动发零速并尝试切 `NoControl`。

不纳入 v1 首次验收:

- 手臂末端轨迹。
- 下肢/躯干控制。
- GUI、Web 控制台、远程任务队列。
- 复杂路径规划或闭环定位导航。

## 2. 产物文件清单

在 `/mnt/e/project/kuavo/kuavo_sim_platform/` 下新增以下文件:

```text
kuavo_sim_platform/
  kuavo_sim/
    __init__.py
    modes.py
    state.py
    base.py
    client.py
    scenario.py
  scripts/
    demo_base_probe.py
    demo_base_forward.py
    demo_stop.py
  scenarios/
    base_probe.yaml
    base_forward.yaml
  tests/
    test_modes.py
    test_scenario_parse.py
  README.md
  requirements.txt
```

首轮不新增 `setup.py` 或 `package.xml`。等 demo 稳定后,再决定是否做成标准 ROS1/catkin 包。

## 3. 阶段 1: 现场确认接口

目的: 把不确定项变成记录,不要靠猜测写服务字段或消息类型。

执行位置: 容器内,且已经 `source /root/kuavo_ws/devel/setup.bash`。

```bash
source /root/kuavo_ws/devel/setup.bash

rostopic info /cmd_vel
rostopic info /cmd_vel_world
rostopic info /cmd_pose
rostopic info /cmd_pose_world
rostopic info /mobile_manipulator/lb_mpc_control_mode
rostopic info /mobile_manipulator_mpc_observation
rostopic info /lb_cmd_pose_reach_time

rosservice info /mobile_manipulator_mpc_control
rossrv show $(rosservice info /mobile_manipulator_mpc_control | awk '/Type/{print $2}')

rosservice info /enable_lb_arm_quick_mode || true
sed -n '1,240p' /root/kuavo_ws/src/demo/test_kuavo_wheel_real/lb_ctrl_api.py
```

记录到 `kuavo_sim_platform/README.md` 的 "Verified Runtime Interfaces" 表:

| 项 | 需要记录 |
|---|---|
| `/cmd_vel` | 实际消息类型,预期 `geometry_msgs/Twist` |
| `/cmd_vel_world` | 实际消息类型 |
| `/cmd_pose` | 实际消息类型和单位 |
| `/cmd_pose_world` | 实际消息类型和单位 |
| `/mobile_manipulator_mpc_control` | srv 类型、请求字段、响应字段 |
| `lb_ctrl_api.py` | 是否可直接 `import lb_ctrl_api` 并调用 `set_control_mode(int)` |
| mode feedback | 类型和取值字段 |
| reach time feedback | 类型和取值字段 |

阶段完成标准:

- 所有 v1 必需接口都有实际类型记录。
- 明确模式切换优先路径: `lb_ctrl_api` 可用则优先复用;不可用才直接调 service。
- 如果 `/cmd_vel` 不是 `geometry_msgs/Twist`,停止实现并先更新本文档。

## 4. 阶段 2: 写最小 Python 包

只实现底盘速度闭环和模式切换,不碰手臂。

### 4.1 `kuavo_sim/modes.py`

职责:

- 定义 `CtrlMode` 枚举。
- 提供 `resolve_mode(value)`。

模式值:

| 名称 | 值 |
|---|---:|
| `NoControl` | 0 |
| `ArmOnly` | 1 |
| `BaseOnly` | 2 |
| `BaseArm` | 3 |
| `ArmEeOnly` | 4 |

验收:

```bash
python3 -m pytest tests/test_modes.py
```

### 4.2 `kuavo_sim/base.py`

职责:

- 发布 `/cmd_vel` 和 `/cmd_vel_world`。
- 提供 `move_for()`、`move_world_for()`、`stop_base()`。
- 对 `x/y/yaw` 做限幅。
- `move_for()` 结束必须显式发零速并保持至少 `0.3s`。

默认限幅:

```python
max_vx = 0.30
max_vy = 0.30
max_wyaw = 0.50
```

首跑参数必须保守:

```python
duration = 1.0
x = 0.05
y = 0.0
yaw = 0.0
```

验收:

- `python3 -m py_compile kuavo_sim_platform/kuavo_sim/base.py` 通过。
- ROS 运行时执行 probe 后机器人只小幅前进,没有持续滑行。

### 4.3 `kuavo_sim/state.py`

职责:

- 订阅 mode feedback。
- 订阅 `/mobile_manipulator_mpc_observation`,只用于判断 MPC 是否在更新。
- 等待 `/cmd_vel` 有订阅者。
- 提供 `wait_ready()` 和 `wait_mode(mode)`。

实现策略:

- 对 observation 使用 `rospy.AnyMsg`,避免依赖具体消息结构。
- mode feedback 类型根据阶段 1 的记录确定;如果不是 `std_msgs/Int32`,按实际类型实现取值。
- v1 不强依赖 reach time,只记录接口,不把它作为底盘速度 demo 的必要条件。

验收:

- MPC 未启动时 `wait_ready(timeout=5)` 返回失败并给出清楚日志。
- MPC 启动后 `wait_ready(timeout=30)` 通过。

### 4.4 `kuavo_sim/client.py`

职责:

- 初始化 ROS node。
- 聚合 `BaseControl` 和 `StateMonitor`。
- 模式切换: `set_mode()`、`set_mode_base_only()`、`set_mode_no_control()`。
- 上下文管理: `with KuavoSim() as bot:` 退出时自动停车和切 `NoControl`。

模式切换策略:

1. 优先导入 `/root/kuavo_ws/src/demo/test_kuavo_wheel_real/lb_ctrl_api.py`。
2. 如果导入成功,调用官方 `set_control_mode(int)`。
3. 如果导入失败,才使用阶段 1 记录的 srv 类型和字段直接调用 `/mobile_manipulator_mpc_control`。
4. 默认 `confirm=True`,切换后必须通过 mode feedback 确认;确认失败抛异常。

验收:

- `set_mode_base_only()` 后 feedback 变为 `2`。
- `set_mode_no_control()` 后 feedback 变为 `0`。
- 异常路径会先 `stop_base()`。

## 5. 阶段 3: Demo 与 YAML 场景

### 5.1 `scripts/demo_base_probe.py`

唯一目的: 首次方向探测。

行为:

```text
wait_ready
set BaseOnly
move_for(duration=1.0, x=0.05)
stop_base
set NoControl
```

运行:

```bash
cd /mnt/e/project/kuavo
python3 kuavo_sim_platform/scripts/demo_base_probe.py
```

验收:

- 机器人向预期的前方小幅移动。
- 结束后无持续速度。
- 如果方向相反,不要继续跑大速度;先在 README 记录实际方向,再决定是否在 wrapper 层取反。

### 5.2 `scripts/demo_base_forward.py`

在 probe 通过后启用。

默认参数:

```python
duration = 2.0
x = 0.20
y = 0.0
yaw = 0.0
```

验收:

- BaseOnly 模式确认成功。
- 机器人前进约 `0.4m` 量级。
- demo 退出后 mode 回到 `NoControl`。

### 5.3 `scripts/demo_stop.py`

紧急停止脚本。

行为:

- 不等待完整 ready。
- 尽快构造 `/cmd_vel` publisher。
- 连续发布零速 `1.0s`。
- 尝试切 `NoControl`;失败只打印错误,不阻塞零速发布。

### 5.4 `kuavo_sim/scenario.py`

支持最小动作:

```yaml
name: base_probe
steps:
  - action: wait_ready
    timeout: 30
  - action: set_mode
    mode: BaseOnly
  - action: move_for
    duration: 1.0
    x: 0.05
  - action: stop_base
  - action: set_mode
    mode: NoControl
```

运行:

```bash
python3 -m kuavo_sim.scenario kuavo_sim_platform/scenarios/base_probe.yaml
```

验收:

- YAML 版本和 Python demo 行为一致。
- 任一步失败时进程非零退出,并执行 fail-safe。
- YAML 未知 action 会报清楚错误。

## 6. 阶段 4: 离线检查与运行检查

每次代码修改后至少执行:

```bash
cd /mnt/e/project/kuavo
python3 -m py_compile \
  kuavo_sim_platform/kuavo_sim/modes.py \
  kuavo_sim_platform/kuavo_sim/base.py \
  kuavo_sim_platform/kuavo_sim/state.py \
  kuavo_sim_platform/kuavo_sim/client.py \
  kuavo_sim_platform/kuavo_sim/scenario.py

python3 -m pytest kuavo_sim_platform/tests
```

如果容器内没有 `pytest`:

```bash
python3 -m unittest discover -s kuavo_sim_platform/tests
```

运行时检查顺序:

```bash
python3 kuavo_sim_platform/scripts/demo_stop.py
python3 kuavo_sim_platform/scripts/demo_base_probe.py
python3 -m kuavo_sim.scenario kuavo_sim_platform/scenarios/base_probe.yaml
python3 kuavo_sim_platform/scripts/demo_base_forward.py
python3 -m kuavo_sim.scenario kuavo_sim_platform/scenarios/base_forward.yaml
```

## 7. 风险与处理策略

| 风险 | 发现方式 | 处理 |
|---|---|---|
| `lb_ctrl_api` import 失败 | `client.py` 启动日志 | 回退到 service proxy,并记录失败原因 |
| mode feedback 类型不是 `Int32` | `rostopic info` | 按实际消息类型改 `state.py` |
| `/cmd_vel` 无订阅者 | `wait_ready()` 超时 | 检查 MuJoCo launch 和 MPC controller 是否启动 |
| 前进方向与约定相反 | `demo_base_probe.py` | 停止大速度测试,记录方向,再决定 wrapper 是否取反 |
| 停止后仍滑行 | demo 结束观察 | 增加零速保持时间,确认是否还有其它控制源发布速度 |
| 直接 service 字段不匹配 | service 调用异常 | 读取 `rossrv show` 和 `lb_ctrl_api.py`,不要猜字段 |

## 8. v1 验收清单

必须全部满足才算 v1 完成:

- [ ] README 记录了阶段 1 的真实接口确认结果。
- [ ] `demo_base_probe.py` 以 `x=0.05,duration=1.0` 成功完成。
- [ ] `demo_base_forward.py` 能稳定前进并停止。
- [ ] YAML `base_probe.yaml` 与 Python probe 行为一致。
- [ ] 任意异常路径会执行 `stop_base()`。
- [ ] 模式切换默认确认 feedback,失败时抛出可读异常。
- [ ] 离线语法检查通过。
- [ ] 单元测试覆盖 mode 解析和 YAML action 校验。
- [ ] 没有修改 MuJoCo、Kuavo 控制器源码、历史产物、导入数据或虚拟环境目录。

## 9. v2 延后项

这些功能等底盘速度链路稳定后再做:

- `/cmd_pose` 与 `/cmd_pose_world` 位姿控制。
- `/lb_cmd_pose_reach_time` 到达时间等待。
- `/kuavo_arm_traj` 14 维手臂关节控制。
- `/mm/two_arm_hand_pose_cmd` 双臂末端控制。
- `setup.py`、`package.xml` 或 catkin 包化。
- GUI/Web/API 服务层。
- 更完整的 scenario 条件、循环、变量和日志回放。

## 10. 推荐当天执行顺序

1. 启动仿真并确认 `ROBOT_VERSION=62`。
2. 执行阶段 1 的所有 `rostopic`/`rosservice`/`sed` 命令。
3. 创建 `kuavo_sim_platform` 文件骨架。
4. 实现 `modes.py`、`base.py`、`state.py`、`client.py`。
5. 先跑 `py_compile` 和 mode 单测。
6. 跑 `demo_stop.py`,确认零速发布无异常。
7. 跑 `demo_base_probe.py`,只用 `x=0.05,duration=1.0`。
8. probe 通过后跑 YAML probe。
9. 再启用 `demo_base_forward.py` 的 `x=0.20,duration=2.0`。
10. 把实际运行结果、方向、模式反馈、任何回填点写入 README。

完成以上步骤后,再把 v2 项拆成独立任务,不要在 v1 调试期间混入手臂、GUI 或包化工作。
