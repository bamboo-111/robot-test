# Kuavo 5-W 脚本控制协作规则

本文档给团队成员使用，目标是在同一套 Windows + WSL2 + Docker Desktop + Kuavo ROS 容器环境里，安全地编写、选择和执行仿真控制脚本。

## 当前基线

- Windows 项目目录：`E:\project\kuavo`
- WSL 发行版：`Ubuntu-20.04`
- Docker 容器：`kuavo5w_sim`
- Docker 镜像：`kuavo-ros-opensource:master`
- Kuavo 仓库挂载：`/root/kuavo_ws`
- 本项目挂载：`/root/kuavo_deploy`
- 默认机器人版本：`ROBOT_VERSION=62`
- 默认 launch：`load_kuavo_mujoco_sim_wheel.launch`

## 快速入口

在 Windows PowerShell 中执行：

```powershell
cd E:\project\kuavo
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/windows/kuavo5w-script-menu.ps1
```

也可以启动本地网页控制台：

```powershell
cd E:\project\kuavo
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/windows/start-kuavo5w-web-control.ps1
```

默认地址：

```text
http://127.0.0.1:8765
```

网页控制台提供和菜单一致的白名单动作：启动或连接、probe、forward、复原、暂停 MPC、恢复 MPC、休眠模拟器、查看日志、选择 YAML 场景。

菜单选项：

| 键 | 动作 |
|---|---|
| `1` | 启动或连接已有模拟器 |
| `2` | 执行安全 probe |
| `3` | 执行底盘前进 demo |
| `4` | 从 `kuavo_sim_platform/scenarios` 选择 YAML 脚本 |
| `R` | 复原：发布零速度并切回 `NoControl` |
| `L` | 查看 MuJoCo 启动日志 |
| `C` | 进入容器 shell |
| `Q` | 退出菜单 |

## 复原键

菜单中按 `R` 会执行复原动作：

1. 发布底盘零速度。
2. 切换到 `NoControl`。
3. 保留容器和模拟器，不重启。

也可以在另一个 PowerShell 窗口随时执行：

```powershell
cd E:\project\kuavo
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/windows/kuavo5w-restore.ps1
```

注意：如果某个脚本正在前台执行，菜单本身不能实时抢占那个进程。需要紧急复原时，打开第二个 PowerShell 窗口执行上面的 `kuavo5w-restore.ps1`。

## 直接命令

启动或连接模拟器：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/windows/start-kuavo5w-platform.ps1
```

安全探测：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/windows/start-kuavo5w-platform.ps1 -RunProbe
```

底盘前进 demo：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/windows/start-kuavo5w-platform.ps1 -Demo forward
```

复原：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/windows/start-kuavo5w-platform.ps1 -Demo stop
```

强制重启 ROS launch：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/windows/start-kuavo5w-platform.ps1 -StopExistingLaunch
```

强制重建容器：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/windows/start-kuavo5w-platform.ps1 -RecreateContainer
```

日常开发不要使用 `-RecreateContainer`，因为当前容器内安装过 OpenVINO；重建容器后需要重新固化或安装 OpenVINO。

## Python SDK 接口

Python 入口包在：

```text
kuavo_sim_platform/kuavo_sim
```

最小示例：

```python
from kuavo_sim_platform.kuavo_sim import KuavoSim

with KuavoSim() as bot:
    bot.wait_ready(timeout=30)
    bot.set_mode_base_only()
    bot.move_for(duration=2.0, x=0.10, y=0.0, yaw=0.0)
    bot.stop_base()
    bot.set_mode_no_control()
```

常用接口：

| 接口 | 说明 |
|---|---|
| `wait_ready(timeout=30)` | 等待 ROS 接口和观测流就绪 |
| `set_mode("BaseOnly")` | 切换模式，使用 `/mobile_manipulator_mpc_control` 确认 |
| `set_mode_base_only()` | 切到底盘控制 |
| `set_mode_no_control()` | 切到无主动控制 |
| `cmd_vel(x, y, yaw)` | 发布一次机体系底盘速度 |
| `cmd_vel_world(x, y, yaw)` | 发布一次世界系底盘速度 |
| `move_for(duration, x, y, yaw, rate=20)` | 持续发布机体系速度，结束后自动停 |
| `move_world_for(duration, x, y, yaw, rate=20)` | 持续发布世界系速度，结束后自动停 |
| `stop_base(hold=0.3)` | 连续发布零速度 |
| `fail_safe()` | 尝试停底盘并切 `NoControl` |

控制模式：

| 名称 | 值 | 用途 |
|---|---:|---|
| `NoControl` | `0` | 无主动控制 |
| `ArmOnly` | `1` | 仅手臂 |
| `BaseOnly` | `2` | 仅底盘 |
| `BaseArm` | `3` | 底盘和手臂 |
| `ArmEeOnly` | `4` | 手臂末端控制 |

## YAML 脚本接口

YAML 脚本放在：

```text
kuavo_sim_platform/scenarios
```

示例：

```yaml
name: base_forward_safe
steps:
  - action: wait_ready
    timeout: 30
  - action: set_mode
    mode: BaseOnly
  - action: move_for
    duration: 2.0
    x: 0.10
    y: 0.0
    yaw: 0.0
  - action: stop_base
    hold: 0.5
  - action: set_mode
    mode: NoControl
```

支持动作：

| action | 参数 | 说明 |
|---|---|---|
| `wait_ready` | `timeout` | 等待运行时就绪 |
| `set_mode` | `mode`, `timeout` | 切换控制模式 |
| `move_for` | `duration`, `x`, `y`, `yaw`, `rate` | 机体系移动 |
| `move_world_for` | `duration`, `x`, `y`, `yaw`, `rate` | 世界系移动 |
| `stop_base` | `hold` | 停止底盘 |

通过菜单选择 YAML：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/windows/kuavo5w-script-menu.ps1
```

选择 `4`，再选择 YAML 文件编号。

直接运行 YAML：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/windows/start-kuavo5w-platform.ps1 -Scenario /root/kuavo_deploy/kuavo_sim_platform/scenarios/base_forward.yaml
```

## 已验证 ROS 接口

| 接口 | 类型 | 说明 |
|---|---|---|
| `/cmd_vel` | `geometry_msgs/Twist` | 机体系底盘速度 |
| `/cmd_vel_world` | `geometry_msgs/Twist` | 世界系底盘速度 |
| `/mobile_manipulator_mpc_control` | `kuavo_msgs/changeTorsoCtrlMode` | 控制模式切换 |
| `/mobile_manipulator_mpc_observation` | `ocs2_msgs/mpc_observation` | MPC 观测流 |
| `/mobile_manipulator/lb_mpc_control_mode` | `std_msgs/Int8` | 运行时模式相关状态，不作为模式切换确认依据 |

模式切换以 `/mobile_manipulator_mpc_control` 的 service response 为准。

## 脚本编写规则

每个运动脚本必须满足：

1. 先 `wait_ready()`。
2. 运动前显式 `set_mode_base_only()` 或其他目标模式。
3. 单次速度不要超过当前安全范围：
   - `abs(x) <= 0.20`
   - `abs(y) <= 0.10`
   - `abs(yaw) <= 0.40`
   - `duration <= 5.0`
4. 每段运动后必须 `stop_base()`。
5. 脚本结尾必须切回 `NoControl`，或使用 `with KuavoSim() as bot:` 依赖上下文退出复原。
6. 不要直接改 Kuavo 官方仓库源码来实现脚本动作。
7. 不要在 `/mnt/c` 或 `/mnt/e` 编译 Kuavo；编译应在 WSL ext4 的 Kuavo 源码目录中做。
8. 团队新增 YAML 时，先从 `base_probe.yaml` 复制，逐步增加速度和时长。

## 协作流程

新增脚本建议流程：

1. 新增 YAML 到 `kuavo_sim_platform/scenarios`。
2. 本地先运行菜单选项 `2`，确认模拟器状态正常。
3. 运行菜单选项 `4` 选择新 YAML。
4. 观察 MuJoCo 和 RViz。
5. 如果行为不符合预期，按 `R` 或在第二个 PowerShell 执行 `kuavo5w-restore.ps1`。
6. 记录新增脚本的目的、预期现象、速度范围和风险。

## 常见问题

如果菜单提示 ROS interfaces not ready：

```powershell
wsl -d Ubuntu-20.04 -- docker exec -it kuavo5w_sim bash -lc 'tail -120 /tmp/kuavo5w_mujoco_start.log'
```

如果窗口没有明显运动，先尝试转向类脚本，因为 yaw 在视觉上更容易确认。

如果容器被重建后又出现 `libopenvino.so` 或 `libdrake.so` 缺失，需要重新安装 OpenVINO 或把它固化进镜像；启动脚本已经补了 `/opt/drake/lib` 和 `/usr/lib` 的运行期库路径。
