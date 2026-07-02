# Kuavo5-W / MuJoCo 远程协作完整说明（给笔记本 B/C）

本文档用于发给笔记本 B/C 的协作者。目标是让 B/C 用户通过笔记本 A 的局域网跳板，安全进入模拟主机的 WSL 环境，查看 Kuavo5-W / MuJoCo / ROS / Docker 仿真状态，并通过 Web 控制台导入和运行脚本。

当前阶段是**Web 控制台协作**。B/C 可以观察、检查、记录状态；需要改变仿真或机器人状态时，通过 Web 控制台执行，并在操作前和其他协作者人工确认，避免多人同时控制。不要直接发布 ROS 命令或重启容器。

## v0.1-alpha 推荐使用流程

1. 先阅读 `docs/v0.1_startup_runbook.md`，按文档区分 Windows PowerShell、WSL Ubuntu、Docker 容器内部和浏览器 Web 控制台。
2. 出错时先查看 `docs/v0.1_recovery_checklist.md`，不要直接重启 WSL、Docker 或容器。
3. 首次操作只运行安全探测和指定 Demo，不运行未知来源脚本。
4. 上传脚本时优先使用 `scripts/import_examples/bc_safe_probe.py`，该脚本只检查 ROS topic/service，不发布 `/cmd_vel`。
5. 遇到问题使用 `docs/v0.1_bc_feedback.template.md` 记录命令输出、截图或日志路径。
6. A/B/C 人工验收分别复制 `docs/v0.1_acceptance_A.template.md`、`docs/v0.1_acceptance_B.template.md`、`docs/v0.1_acceptance_C.template.md` 后填写，不要直接把真实结果写进模板。

v0.1-alpha 交接文档入口：

- `docs/v0.1_startup_runbook.md`
- `docs/v0.1_recovery_checklist.md`
- `docs/v0.1_release_checklist.md`
- `docs/v0.1_bc_feedback.template.md`

## 1. 项目目的

这套远程协作方案的目的：

- 让 B/C 用户通过笔记本 A 的局域网跳板 SSH 进入模拟主机 WSL。
- 在 WSL 中查看 Docker、ROS、MuJoCo、Kuavo5-W 仿真状态。
- 在 Web 控制台中导入和运行 Python 脚本。
- 在 Web 控制台中执行授权的仿真控制动作。
- 不直接暴露 ROS master。
- 不让 B/C 直接连接 ROS `11311`。
- 高频控制、MuJoCo 仿真、ROS 节点仍然在模拟主机本地运行。

换句话说，B/C 的角色是“Web 控制台操作者”：平时可以观察和检查；需要控制时通过 Web 控制台操作，并与其他协作者人工协调。

## 2. 当前已知环境

模拟主机：

| 项 | 当前值 |
|---|---|
| 主机系统 | Windows |
| Linux 环境 | WSL2 Ubuntu-20.04 |
| WSL 用户 | `bamboo` |
| WSL hostname | `bamboo` |
| WSL IP | `172.20.227.93` |
| Docker 容器 | `kuavo5w_sim` |
| 容器状态 | `Up` |
| Docker 镜像 | `kuavo-ros-opensource:master` |
| 默认机器人版本 | `ROBOT_VERSION=62` |
| 默认 MuJoCo launch | `load_kuavo_mujoco_sim_wheel.launch` |
| Windows 项目目录 | `E:\project\kuavo` |
| WSL 项目目录 | `/mnt/e/project/kuavo` |
| Kuavo 源码目录 | `/home/bamboo/kuavo_ws_src/kuavo-ros-opensource` |
| 容器内 Kuavo 工作区 | `/root/kuavo_ws` |
| 容器内本项目挂载 | `/root/kuavo_deploy` |

容器内 ROS 环境 source 路径：

```bash
source /root/kuavo_ws/installed/setup.bash
source /root/kuavo_ws/devel/setup.bash
```

当前 GPU renderer 已验证：

```text
OpenGL renderer string: D3D12 (NVIDIA GeForce RTX 4070 SUPER)
Accelerated: yes
```

当前 OpenVINO 已固化进镜像：

```text
OpenVINO 2025.2.0
libopenvino.so.2520 available
```

## 3. 当前远程链路

模拟主机 Windows 端口代理：

```text
127.0.0.1:2222 -> 172.20.227.93:22
```

模拟主机本机已验证：

```powershell
ssh -i "$env:USERPROFILE\.ssh\kuavo_wsl_ed25519" -p 2222 bamboo@127.0.0.1
```

笔记本 A 远程链路：

```text
笔记本 A 本机 127.0.0.1:2222
  -> UU 远程端口映射
  -> 模拟主机 Windows 127.0.0.1:2222
```

笔记本 A 已验证：

```powershell
ssh -i "$env:USERPROFILE\.ssh\kuavo_laptopA_ed25519" -p 2222 bamboo@127.0.0.1
```

笔记本 A 局域网跳板：

```text
笔记本 A 局域网 IP：192.168.1.109
笔记本 A 跳板端口：192.168.1.109:3222 -> 127.0.0.1:2222
```

B/C 通过以下方式连接：

```powershell
ssh -i "$env:USERPROFILE\.ssh\<自己的私钥文件>" -p 3222 bamboo@192.168.1.109
```

完整链路结构：

```text
笔记本 B/C
  -> 笔记本 A 192.168.1.109:3222
  -> 笔记本 A 127.0.0.1:2222
  -> UU 远程端口映射
  -> 模拟主机 Windows 127.0.0.1:2222
  -> WSL Ubuntu-20.04 172.20.227.93:22
  -> bamboo 用户
  -> Docker 容器 kuavo5w_sim
  -> ROS / MuJoCo / Kuavo5-W 仿真环境
```

## 4. 用户角色说明

模拟主机：

- 运行 WSL2、Docker Desktop、MuJoCo、ROS、Kuavo5-W 仿真。
- 承载真正的仿真状态和控制进程。

笔记本 A：

- 远程连接主机。
- 同时作为 B/C 的局域网跳板。
- 当前推荐权限：主控 / 跳板。

笔记本 B/C：

- 通过 A 的 `192.168.1.109:3222` 连接到 WSL。
- 当前推荐权限：状态检查 + Web 控制台控制。
- B/C 可以通过 Web 控制台导入脚本、运行脚本、运行场景或执行 pause/resume 等控制动作；操作前需要确认没有其他人正在控制。

## 5. B/C 准备工作

B/C 用户需要：

1. 与笔记本 A 在同一个局域网。
2. 确认能访问 A 的 IP：`192.168.1.109`。
3. 在自己的电脑生成 SSH key。
4. 只把 `.pub` 公钥发给主机维护者或 A。
5. 不要把私钥发给任何人。
6. 不要使用 A 或模拟主机的私钥。

### 5.1 笔记本 B 生成 SSH key

在 B 的 Windows PowerShell 中运行：

```powershell
mkdir "$env:USERPROFILE\.ssh" -Force

ssh-keygen -t ed25519 `
  -f "$env:USERPROFILE\.ssh\kuavo_laptopB_ed25519" `
  -C "kuavo-laptop-B"

Get-Content "$env:USERPROFILE\.ssh\kuavo_laptopB_ed25519.pub"
```

把最后一条命令输出的整行 `.pub` 公钥发给维护者。

### 5.2 笔记本 C 生成 SSH key

在 C 的 Windows PowerShell 中运行：

```powershell
mkdir "$env:USERPROFILE\.ssh" -Force

ssh-keygen -t ed25519 `
  -f "$env:USERPROFILE\.ssh\kuavo_laptopC_ed25519" `
  -C "kuavo-laptop-C"

Get-Content "$env:USERPROFILE\.ssh\kuavo_laptopC_ed25519.pub"
```

把最后一条命令输出的整行 `.pub` 公钥发给维护者。

注意：

- `.pub` 是公钥，可以发给维护者。
- 没有 `.pub` 后缀的是私钥，不能发送、不能截图、不能共享。
- 维护者会把公钥加入 WSL 的 `/home/bamboo/.ssh/authorized_keys`。

## 6. B/C 连接命令

笔记本 B：

```powershell
ssh -i "$env:USERPROFILE\.ssh\kuavo_laptopB_ed25519" -p 3222 bamboo@192.168.1.109
```

笔记本 C：

```powershell
ssh -i "$env:USERPROFILE\.ssh\kuavo_laptopC_ed25519" -p 3222 bamboo@192.168.1.109
```

首次连接如果出现 host key fingerprint，只有在确认目标确实是 A 的 `192.168.1.109:3222` 时才输入：

```text
yes
```

## 7. 登录后的基础只读检查

登录后先运行：

```bash
whoami
hostname
hostname -I
pwd
date
w
```

预期：

- `whoami` 是 `bamboo`。
- `hostname` 是 `bamboo`。
- `hostname -I` 中能看到 `172.20.227.93`。

检查 Docker：

```bash
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"
```

预期：

- 能看到 `kuavo5w_sim`。
- 状态为 `Up`。

检查仿真进程：

```bash
docker exec kuavo5w_sim bash -lc 'ps aux | grep -Ei "mujoco|ros|kuavo|python|mpc|nodelet" | grep -v grep'
```

检查 ROS 节点：

```bash
docker exec kuavo5w_sim bash -lc 'source /root/kuavo_ws/installed/setup.bash; source /root/kuavo_ws/devel/setup.bash; rosnode list | sort'
```

检查 ROS topic：

```bash
docker exec kuavo5w_sim bash -lc 'source /root/kuavo_ws/installed/setup.bash; source /root/kuavo_ws/devel/setup.bash; rostopic list | sort | head -120'
```

检查 ROS service：

```bash
docker exec kuavo5w_sim bash -lc 'source /root/kuavo_ws/installed/setup.bash; source /root/kuavo_ws/devel/setup.bash; rosservice list | sort | grep -Ei "mobile_manipulator|mpc|kuavo|mujoco|control"'
```

只读查看 `/mobile_manipulator_mpc_control`：

```bash
docker exec kuavo5w_sim bash -lc 'source /root/kuavo_ws/installed/setup.bash; source /root/kuavo_ws/devel/setup.bash; rosservice info /mobile_manipulator_mpc_control'
```

只读查看 service 类型：

```bash
docker exec kuavo5w_sim bash -lc 'source /root/kuavo_ws/installed/setup.bash; source /root/kuavo_ws/devel/setup.bash; rosservice type /mobile_manipulator_mpc_control'
```

检查 OpenGL renderer：

```bash
docker exec kuavo5w_sim bash -lc 'glxinfo -B | grep -Ei "OpenGL renderer|Accelerated|OpenGL version" || true'
```

## 8. `rostopic echo` 安全说明

`rostopic echo` 可能会卡住。原因通常是：

- topic 没有发布者；
- topic 暂时没有消息；
- `rostopic echo -n 1` 一直在等第一条消息。

规则：

- 所有 `rostopic echo` 都加 `timeout`。
- 卡住时按 `Ctrl+C` 退出。
- 优先用 `rostopic info`、`rostopic hz` 判断状态。

安全检查 `/joint_states` 是否存在：

```bash
docker exec kuavo5w_sim bash -lc 'source /root/kuavo_ws/installed/setup.bash; source /root/kuavo_ws/devel/setup.bash; rostopic list | grep -E "^/joint_states$|joint"'
```

检查 `/joint_states` 发布者：

```bash
docker exec kuavo5w_sim bash -lc 'source /root/kuavo_ws/installed/setup.bash; source /root/kuavo_ws/devel/setup.bash; rostopic info /joint_states'
```

检查 `/joint_states` 频率：

```bash
docker exec kuavo5w_sim bash -lc 'source /root/kuavo_ws/installed/setup.bash; source /root/kuavo_ws/devel/setup.bash; timeout 5 rostopic hz /joint_states'
```

安全读取 `/joint_states`：

```bash
docker exec kuavo5w_sim bash -lc 'source /root/kuavo_ws/installed/setup.bash; source /root/kuavo_ws/devel/setup.bash; timeout 5 rostopic echo -n 1 /joint_states'
```

安全读取 `/clock`：

```bash
docker exec kuavo5w_sim bash -lc 'source /root/kuavo_ws/installed/setup.bash; source /root/kuavo_ws/devel/setup.bash; timeout 5 rostopic echo -n 3 /clock'
```

安全读取 `/tf`：

```bash
docker exec kuavo5w_sim bash -lc 'source /root/kuavo_ws/installed/setup.bash; source /root/kuavo_ws/devel/setup.bash; timeout 5 rostopic echo -n 1 /tf'
```

## 9. 当前项目目录说明

当前项目在模拟主机 Windows 上位于：

```text
E:\project\kuavo
```

在 WSL 中位于：

```text
/mnt/e/project/kuavo
```

主要目录：

```text
docs/                         项目说明、协作规则、Web 导入指南
scripts/windows/              Windows PowerShell 启动、菜单、Web 控制脚本
scripts/wsl/                  WSL 侧构建、clone、容器启动脚本
scripts/container/            容器内 build/start/test-gui 脚本
kuavo_sim_platform/           Python/YAML 脚本控制平台
kuavo_sim_platform/kuavo_sim/ Python SDK 封装
kuavo_sim_platform/scripts/   demo 和接口检查脚本
kuavo_sim_platform/scenarios/ YAML 场景
kuavo_sim_platform/web_control/ 本地 Web 控制台
kuavo_sim_platform/imported_scripts/ Web 导入的 Python 脚本
backups/                      修改前备份
```

已有相关文档：

```text
docs/windows-kuavo5w-docker.md
docs/kuavo-sim-platform-collaboration.md
docs/kuavo-web-import-script-guide.md
docs/kuavo-sim-script-platform-task.md
docs/Kuavo 5-W Script Control Platform — 完整实现 v1.md
kuavo_sim_platform/README.md
```

B/C 当前只需要阅读本文档。其他文档给主机维护者、脚本开发者或 A 使用。

## 10. Web 控制台和维护入口

以下 Windows PowerShell 命令通常由模拟主机或 A 执行，用来启动 Web 控制台或维护仿真环境。B/C 主要通过浏览器使用 Web 控制台，不直接运行这些 Windows 端维护脚本。

Windows PowerShell 中启动或连接平台：

```powershell
cd E:\project\kuavo
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/windows/start-kuavo5w-platform.ps1
```

启动 MuJoCo 前台 launch：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/windows/start-kuavo5w-mujoco.ps1
```

脚本菜单：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/windows/kuavo5w-script-menu.ps1
```

Web 控制台：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/windows/start-kuavo5w-web-control.ps1
```

默认 Web 地址：

```text
http://127.0.0.1:8765
```

B/C 可以使用 Web 控制台执行动作，但必须遵守：

1. 操作前确认没有其他协作者正在控制仿真。
2. 导入脚本、运行脚本、运行场景或执行 pause/resume 等动作都通过 Web 控制台完成。
3. 控制结束后在协作群或当前沟通渠道说明已结束。

Web 后端仍会串行执行控制命令；如果已有命令正在运行，新的命令会返回 busy/409 类结果。

## 11. 脚本控制平台概览

本项目提供轻量 Python/YAML 控制平台，目录：

```text
kuavo_sim_platform/
```

核心 Python 包：

```text
kuavo_sim_platform/kuavo_sim
```

常见模块：

| 文件 | 作用 |
|---|---|
| `client.py` | `KuavoSim` 主入口 |
| `modes.py` | 控制模式枚举和解析 |
| `base.py` | 底盘速度、位姿、停止接口 |
| `arm.py` | 手臂、末端、IK/FK 相关封装 |
| `lower_body.py` | 下肢 / 躯干 |
| `head_hand.py` | 头部 / 手部 / 夹爪 |
| `state.py` | readiness 和状态等待 |
| `scenario.py` | YAML 场景运行器 |

典型 Python 示例：

```python
from kuavo_sim_platform.kuavo_sim import KuavoSim

with KuavoSim() as bot:
    bot.wait_ready(timeout=30)
    bot.set_mode_base_only()
    bot.move_for(duration=1.0, x=0.05, y=0.0, yaw=0.0)
    bot.stop_base()
    bot.set_mode_no_control()
```

这类脚本会改变仿真状态。B/C 可以通过 Web 控制台运行；操作前需要人工确认没有其他人正在控制，不要直接在 SSH 里运行。

## 12. YAML 场景平台概览

YAML 场景目录：

```text
kuavo_sim_platform/scenarios
```

当前示例：

```text
base_probe.yaml
base_forward.yaml
```

典型 YAML：

```yaml
name: base_forward_safe
steps:
  - action: wait_ready
    timeout: 30
  - action: set_mode
    mode: BaseOnly
  - action: move_for
    duration: 1.0
    x: 0.05
    y: 0.0
    yaw: 0.0
  - action: stop_base
    hold: 0.5
  - action: set_mode
    mode: NoControl
```

支持动作包括：

| action | 说明 |
|---|---|
| `wait_ready` | 等待 ROS / MPC / 控制接口就绪 |
| `set_mode` | 切换控制模式 |
| `move_for` | 机体系底盘速度移动 |
| `move_world_for` | 世界系底盘速度移动 |
| `stop_base` | 发布零速度 |

B/C 可以通过 Web 控制台执行 YAML 场景。操作前需要人工确认没有其他人正在控制，不要直接在 SSH 里运行场景。

## 13. 已确认 ROS 接口

当前 `kuavo5w_sim` 中已确认的常见 topic：

| Topic | 类型 / 说明 |
|---|---|
| `/cmd_vel` | `geometry_msgs/Twist`，机体系底盘速度 |
| `/cmd_vel_world` | `geometry_msgs/Twist`，世界系底盘速度 |
| `/cmd_pose` | 底盘位姿目标 |
| `/cmd_pose_world` | 世界系底盘位姿目标 |
| `/kuavo_arm_traj` | `sensor_msgs/JointState`，14 维上肢关节 |
| `/mm/two_arm_hand_pose_cmd` | 双臂末端位姿命令 |
| `/lb_leg_traj` | 下肢 / 轮臂关节 |
| `/cmd_lb_torso_pose` | 躯干位姿 |
| `/control_robot_hand_position` | 灵巧手位置 |
| `/kuavo_head_body_orientation` | 头部 / 身体姿态 |
| `/mobile_manipulator/lb_mpc_control_mode` | MPC 控制模式相关状态 |

当前常见 service：

| Service | 说明 |
|---|---|
| `/mobile_manipulator_mpc_control` | 主控制模式切换 |
| `/mobile_manipulator_get_mpc_control_mode` | 查询主模式 |
| `/mobile_manipulator_mpc_pause_resume` | 暂停 / 恢复 MPC |
| `/mobile_manipulator_mpc_reset` | MPC reset |
| `/enable_lb_arm_quick_mode` | quick mode |
| `/wheel_arm_change_arm_ctrl_mode` | 5-W 臂控制模式 |
| `/change_arm_ctrl_mode` | 臂控制模式 |
| `/ik/two_arm_hand_pose_cmd_srv` | 双臂 IK |
| `/ik/fk_srv` | 双臂 FK |
| `/execute_arm_action` | 执行预设动作 |

B/C 可以用 `rosservice info`、`rosservice type` 查看信息。需要调用会改变状态的 service 时，应通过 Web 控制台或脚本平台执行，不要在 SSH 里直接 `rosservice call`。

## 14. 控制模式参考

主控制模式：

```text
0 NoControl
1 ArmOnly
2 BaseOnly
3 BaseArm
4 ArmEeOnly
```

5-W 臂控制模式：

```text
0 keep current control position
1 reset arm to initial target
2 external controller
```

Quick mode：

```text
0 off
1 lower-body quick
2 arm quick
3 lower-body + arm quick
```

这些值用于理解日志和接口。B/C 需要切换模式时，应通过 Web 控制台或导入脚本执行。

## 15. Web 导入脚本说明（给维护者 / 脚本开发者）

Web 导入脚本保存到：

```text
kuavo_sim_platform/imported_scripts/
```

脚本在容器内运行位置：

```text
/root/kuavo_deploy
```

导入脚本可以使用：

- 本项目 `kuavo_sim.KuavoSim`
- 官方 `kuavo_humanoid_sdk`
- 官方 5-W 示例封装 `/root/kuavo_ws/src/demo/test_kuavo_wheel_real/lb_ctrl_api.py`
- ROS1 `rospy`、topic、service

脚本文件要求：

- 必须是 `.py` 后缀。
- 文件名只能用 ASCII 字母、数字、点、短横线、下划线。
- 文件名必须以字母或数字开头。
- 单文件大小上限 512 KiB。

B/C 可以通过 Web 控制台导入和运行脚本。后端不再要求 token，但仍会串行执行控制命令，避免同一时刻多个命令并发运行。

## 16. 重要脚本经验和坑点

这些内容来自当前项目调试经验，用于降低 B/C 写脚本和运行脚本时的误操作风险。

### 16.1 5-W 手臂关节值是角度，不是弧度

`/kuavo_arm_traj` 的 `sensor_msgs/JointState.position` 使用角度量级，例如：

```python
[-30.0, 20.0, 15.0, -45.0, 25.0, 10.0, -35.0]
```

不要按弧度写小数，否则动作会非常小或不明显。

### 16.2 `/kuavo_arm_traj` 14 维顺序不能猜

当前理解：

```text
left  = [l_arm_pitch, l_arm_roll, l_arm_yaw, l_forearm, l_hand_yaw, l_hand_roll, l_hand_pitch]
right = [r_arm_pitch, r_arm_roll, r_arm_yaw, r_forearm, r_hand_yaw, r_hand_roll, r_hand_pitch]
arms14 = left + right
```

顺序猜错会导致手臂绕到奇怪方向。

### 16.3 手臂外部控制模式很关键

发布 `/kuavo_arm_traj` 前通常需要：

```python
bot.set_mode_arm_only()
bot.set_arm_control_mode(2)
```

这类命令会改变仿真控制状态。B/C 需要执行时，应写入导入脚本，并通过 Web 控制台运行。

### 16.4 `rostopic echo`、reach-time 等待可能卡住

某些 topic 不一定持续刷新。连续动作不应盲目等待 reach-time topic；只读观察也要使用 `timeout`。

## 17. 明确禁止事项

B/C 当前禁止绕过 Web 控制台直接执行以下命令或动作：

- `rostopic pub`
- `rosservice call`
- 任何 `reset`
- 任何 `pause`
- 任何 `start`
- 任何 `stop`
- 任何 `walk`
- 任何修改 `/cmd_vel` 的命令
- `rosservice call /mobile_manipulator_mpc_control ...`
- 直接在 SSH 中运行 `demo_base_forward.py`
- 直接在 SSH 中运行 YAML 场景
- 直接使用菜单执行动作

B/C 始终禁止执行以下 Docker 破坏性或维护性命令，除非主机维护者明确授权：

- `docker restart kuavo5w_sim`
- `docker stop kuavo5w_sim`
- `docker compose down`
- 删除容器、镜像、数据卷或日志

原因：

- 这些命令会改变仿真状态。
- 绕过 Web 控制台会导致多人同时控制和状态混乱。
- 可能打断其他人的实验。
- Docker 级维护动作会影响所有协作者。

## 18. 常见故障排查

### 18.1 `Test-NetConnection 192.168.1.109 -Port 3222` 不通

B/C 在 Windows PowerShell 中运行：

```powershell
Test-NetConnection 192.168.1.109 -Port 3222
```

可能原因：

- B/C 不在 A 的同一局域网。
- A 没有开启跳板。
- A 的防火墙阻止 3222。
- A 的 UU 映射断开。
- A 的 IP 变化。
- A 没有保持在线。

### 18.2 SSH 提示 `Identity file not accessible`

可能原因：

- 本机没有对应私钥。
- 私钥文件名写错。
- 路径写错。

检查：

```powershell
Test-Path "$env:USERPROFILE\.ssh\kuavo_laptopB_ed25519"
Get-ChildItem "$env:USERPROFILE\.ssh"
```

C 用户把文件名换成：

```powershell
kuavo_laptopC_ed25519
```

### 18.3 SSH `Permission denied`

可能原因：

- 公钥没有加入 WSL `authorized_keys`。
- 用错私钥。
- 用户名不是 `bamboo`。
- 连接到了错误机器。

把完整报错发给维护者。

### 18.4 SSH 成功但 `docker ps` 权限失败

可能原因：

- 当前 `bamboo` 用户没有 Docker 权限。

不要自行修改 Docker 用户组。把报错发给维护者。

### 18.5 `rostopic echo` 卡住

处理方式：

- 按 `Ctrl+C`。
- 换用本文档的 `timeout 5 rostopic echo ...`。
- 先用 `rostopic info` 和 `rostopic hz` 判断 topic 是否活跃。

### 18.6 A 的 IP 变化

如果 `192.168.1.109` 变化：

- B/C 需要使用新的 A 局域网 IP。
- A 端可能需要重新配置跳板监听地址。
- 先在协作群里确认新 IP。

## 19. 协作流程建议

推荐流程：

1. 进入会议或协作群。
2. 确认 A 在线。
3. 确认 A 当前 IP。
4. B/C 执行 SSH 登录。
5. 登录后只运行只读状态检查。
6. 如果需要控制仿真，先向主控申请。
7. 没有明确授权前，不执行任何控制命令。
8. 测试完成后退出 SSH：

```bash
exit
```

## 20. B/C 接入验收标准

B/C 成功接入的标准：

1. `Test-NetConnection 192.168.1.109 -Port 3222` 返回 `TcpTestSucceeded = True`。
2. SSH 能登录 `bamboo@192.168.1.109`。
3. `whoami` 返回 `bamboo`。
4. `docker ps` 能看到 `kuavo5w_sim Up`。
5. `rosnode list` 成功。
6. `rostopic list` 成功。
7. `rosservice info /mobile_manipulator_mpc_control` 成功。
8. 没有执行任何改变仿真状态的命令。

## 21. 一页快速开始

### B 用户

在 Windows PowerShell 中生成 key：

```powershell
mkdir "$env:USERPROFILE\.ssh" -Force

ssh-keygen -t ed25519 `
  -f "$env:USERPROFILE\.ssh\kuavo_laptopB_ed25519" `
  -C "kuavo-laptop-B"

Get-Content "$env:USERPROFILE\.ssh\kuavo_laptopB_ed25519.pub"
```

把 `.pub` 输出发给维护者。维护者确认添加后：

```powershell
Test-NetConnection 192.168.1.109 -Port 3222
ssh -i "$env:USERPROFILE\.ssh\kuavo_laptopB_ed25519" -p 3222 bamboo@192.168.1.109
```

### C 用户

在 Windows PowerShell 中生成 key：

```powershell
mkdir "$env:USERPROFILE\.ssh" -Force

ssh-keygen -t ed25519 `
  -f "$env:USERPROFILE\.ssh\kuavo_laptopC_ed25519" `
  -C "kuavo-laptop-C"

Get-Content "$env:USERPROFILE\.ssh\kuavo_laptopC_ed25519.pub"
```

把 `.pub` 输出发给维护者。维护者确认添加后：

```powershell
Test-NetConnection 192.168.1.109 -Port 3222
ssh -i "$env:USERPROFILE\.ssh\kuavo_laptopC_ed25519" -p 3222 bamboo@192.168.1.109
```

### 登录后只运行这些只读命令

```bash
whoami
hostname -I
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"
docker exec kuavo5w_sim bash -lc 'source /root/kuavo_ws/installed/setup.bash; source /root/kuavo_ws/devel/setup.bash; rosnode list | sort'
docker exec kuavo5w_sim bash -lc 'source /root/kuavo_ws/installed/setup.bash; source /root/kuavo_ws/devel/setup.bash; rosservice info /mobile_manipulator_mpc_control'
docker exec kuavo5w_sim bash -lc 'glxinfo -B | grep -Ei "OpenGL renderer|Accelerated|OpenGL version" || true'
```

牢记：

- 不要共享私钥。
- 不要执行控制命令。
- 不要发布 ROS topic。
- 不要调用会改变状态的 ROS service。
- 不要重启或停止 Docker 容器。

## 22. Web 导入脚本完整指南

以下内容已经从 docs/kuavo-web-import-script-guide.md 合并进本文档。B/C 按本文档操作即可，不需要额外打开其他文档。

本文档给通过网页控制端导入和运行 Python 脚本的开发者使用。导入脚本不是只能控制底盘；脚本在容器内运行，可以直接使用：

- 本项目轻量封装：`kuavo_sim.KuavoSim`
- 官方 SDK：`kuavo_humanoid_sdk`
- 官方 5-W 示例封装：`/root/kuavo_ws/src/demo/test_kuavo_wheel_real/lb_ctrl_api.py`
- ROS1 topic/service：`rospy`、`rostopic`、`rosservice`

### 运行环境

网页导入后的脚本保存到：

```text
kuavo_sim_platform/imported_scripts/
```

脚本运行位置：

```text
/root/kuavo_deploy
```

容器内 Kuavo 工作区：

```text
/root/kuavo_ws
```

官方 SDK 源码和示例：

```text
/root/kuavo_ws/src/kuavo_humanoid_sdk/
/root/kuavo_ws/src/kuavo_humanoid_sdk/examples/atomic_skills/
/root/kuavo_ws/src/demo/test_kuavo_wheel_real/
```

### 文件要求

- 文件必须是 `.py` 后缀。
- 文件名只能使用 ASCII 字母、数字、点、短横线、下划线。
- 文件名必须以字母或数字开头。
- 单个脚本大小上限为 512 KiB。

### 推荐入口模板

```python
#!/usr/bin/env python3
"""Imported Kuavo script."""

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from kuavo_sim import KuavoSim


def main():
    with KuavoSim() as bot:
        bot.wait_ready(timeout=30.0)
        bot.set_mode_base_only()
        bot.move_for(duration=0.5, x=0.03, y=0.0, yaw=0.0)
        bot.stop_base()
        bot.set_mode_no_control()


if __name__ == "__main__":
    main()
```

### 官方 SDK 初始化

官方 SDK 必须先初始化：

```python
from kuavo_humanoid_sdk import KuavoSDK, KuavoRobot

if not KuavoSDK().Init():
    raise RuntimeError("Init KuavoSDK failed")

robot = KuavoRobot()
```

需要 IK/FK 时使用：

```python
from kuavo_humanoid_sdk import KuavoSDK

KuavoSDK().Init(options=KuavoSDK.Options.WithIK)
```

官方文档明确要求：运行 SDK 示例前必须先启动机器人或仿真，否则 SDK 不能正常工作。

### 官方 SDK 常用类

从 `kuavo_humanoid_sdk` 导入：

```python
from kuavo_humanoid_sdk import (
    KuavoSDK,
    KuavoRobot,
    KuavoRobotInfo,
    KuavoRobotState,
    KuavoRobotVision,
    DexterousHand,
    TouchDexterousHand,
    LejuClaw,
)
```

常见用途：

- `KuavoSDK`：SDK 初始化，`Init()`、`DisableLogging()`。
- `KuavoRobot`：机器人运动、头部、手臂、位姿、MPC、IK/FK。
- `KuavoRobotInfo`：机器人型号、版本、关节名、末端类型。
- `KuavoRobotState`：里程计、状态等待、传感状态。
- `KuavoRobotVision`：AprilTag 等视觉数据。
- `DexterousHand`：灵巧手。
- `TouchDexterousHand`：触觉灵巧手。
- `LejuClaw`：二指夹爪。

### 官方 KuavoRobot 方法清单

运动/姿态：

```python
robot.stance()                         # 站立
robot.trot()                           # 小跑/步态
robot.walk(linear_x, linear_y, angular_z)
robot.jump()
robot.squat(height, pitch=0.0)
robot.step_by_step(target_pose, dt=0.4, is_left_first_default=True, collision_check=True)
robot.control_command_pose(x, y, z, yaw)
robot.control_command_pose_world(x, y, z, yaw)
robot.control_command_pose_world_stamped(pos_world)
robot.control_torso_pose(x, y, z, roll, pitch, yaw)
robot.control_wheel_lower_joint(joint_traj)
robot.wheel_control()
```

头部/腰部：

```python
robot.control_head(yaw, pitch)         # yaw [-1.396, 1.396], pitch [-0.436, 0.436], radians
robot.enable_head_tracking(target_id)
robot.disable_head_tracking()
robot.control_waist_pos(joint_positions)
```

手臂：

```python
robot.arm_reset()
robot.manipulation_mpc_reset()
robot.control_arm_joint_positions(joint_positions)
robot.control_arm_joint_trajectory(times, q_frames)
robot.control_arm_target_poses(times, q_frames)  # deprecated, prefer trajectory
robot.set_fixed_arm_mode()
robot.set_auto_swing_arm_mode()
robot.set_external_control_arm_mode()
robot.set_manipulation_mpc_mode(ctrl_mode)
robot.set_manipulation_mpc_control_flow(control_flow)
robot.set_manipulation_mpc_frame(frame)
robot.control_robot_end_effector_pose(left_pose, right_pose, frame)
robot.control_hand_wrench(left_wrench, right_wrench)
```

IK/FK：

```python
robot.arm_ik(left_pose, right_pose, left_elbow_pos_xyz=[0,0,0], right_elbow_pos_xyz=[0,0,0], arm_q0=None, params=None)
robot.arm_ik_free(left_pose, right_pose, left_elbow_pos_xyz=[0,0,0], right_elbow_pos_xyz=[0,0,0], arm_q0=None, params=None)
robot.arm_fk(q)
```

电机/安全：

```python
robot.change_motor_param(motor_param)
robot.get_motor_param()
robot.enable_base_pitch_limit(enable)
robot.is_arm_collision()
robot.set_arm_collision_mode(enable)
robot.wait_arm_collision_complete()
robot.release_arm_collision_mode()
```

### 官方末端执行器

LejuClaw：

```python
from kuavo_humanoid_sdk import KuavoSDK, LejuClaw

KuavoSDK().Init()
claw = LejuClaw()
claw.open()
claw.close()
claw.control_left([50])
claw.control_right([80])
claw.control([20, 100])
claw.wait_for_finish(timeout=2.5)
claw.get_state()
claw.get_position()
claw.get_velocity()
claw.get_effort()
claw.get_grasping_state()
```

DexterousHand：

```python
from kuavo_humanoid_sdk import KuavoSDK, DexterousHand

KuavoSDK().Init()
hand = DexterousHand()
hand.control_left([5, 5, 95, 95, 95, 95])
hand.control_right([5, 5, 95, 95, 95, 5])
hand.control([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
hand.open()
hand.make_gesture(l_gesture_name="thumbs-up", r_gesture_name="ok")
hand.get_gesture_names()
hand.get_state()
hand.get_position()
hand.get_velocity()
hand.get_effort()
hand.get_grasping_state()
```

TouchDexterousHand：

```python
from kuavo_humanoid_sdk import TouchDexterousHand

touch_hand = TouchDexterousHand()
touch_hand.get_touch_state()
touch_hand.get_dexhand_gesture_state()
touch_hand.make_gesture_sync("thumbs-up", "ok", timeout=5.0)
```

### 官方 5-W lb_ctrl_api

容器内路径：

```text
/root/kuavo_ws/src/demo/test_kuavo_wheel_real/lb_ctrl_api.py
```

导入方式：

```python
import sys
sys.path.insert(0, "/root/kuavo_ws/src/demo/test_kuavo_wheel_real")
import lb_ctrl_api as ct
```

已确认函数：

```python
ct.set_control_mode(target_mode)              # 0 NoControl, 1 ArmOnly, 2 BaseOnly, 3 BaseArm, 4 ArmEeOnly
ct.set_arm_control_mode(control_mode)         # 0 keep, 1 reset, 2 external controller
ct.set_arm_quick_mode(quickMode)              # 0 off, 1 lower-body, 2 arm, 3 both
ct.set_mpc_obs_update_mode(obs_update_mode)
ct.get_torso_initial_pose(need_pose=True)
ct.set_ruckig_planner_params(planner_index, ...)
ct.send_timed_single_command(planner_index, ...)
ct.send_timed_multi_commands(timed_cmd_vec, is_sync=False)
ct.reset_torso_to_initial()
ct.set_focus_ee(focus_ee)
ct.set_focus_z(focus_z)
ct.set_lb_multi_timed_offline_traj(offline_trajectories)
ct.set_offline_trajectory_enable(enable)
ct.check_target_pose_reachable(is_left, is_local, is_whole_body, ...)
ct.check_target_pose_reachable_with_fallback(is_left, is_local, is_whole_body, ...)
ct.get_ee_pose_reach_error(is_left)
```

### 本项目 KuavoSim 封装

本项目封装更薄，适合网页导入脚本和 YAML 场景。

底盘：

```python
bot.wait_ready(timeout=30.0)
bot.cmd_vel(x=0.05, y=0.0, yaw=0.0)
bot.cmd_vel_world(x=0.05, y=0.0, yaw=0.0)
bot.move_for(duration=1.0, x=0.05, y=0.0, yaw=0.0)
bot.move_world_for(duration=1.0, x=0.05, y=0.0, yaw=0.0)
bot.stop_base()
bot.cmd_pose(x=0.1, y=0.0, yaw=0.0)
bot.cmd_pose_world(x=0.1, y=0.0, yaw=0.0)
bot.wait_pose_reached(timeout=10.0)
```

主模式：

```python
bot.set_mode_no_control()
bot.set_mode_arm_only()
bot.set_mode_base_only()
bot.set_mode_base_arm()
bot.set_mode_arm_ee_only()
bot.set_mode(0)  # also accepts 0..4 or mode names
```

手臂/末端：

```python
bot.set_arm_control_mode(2)
bot.arm_joint([0.0] * 14)
bot.wait_arm_joint_reached(timeout=10.0)

left = {"xyz": [0.1, 0.4, 0.7], "ypr": [0.0, 0.0, 0.0]}
right = {"xyz": [0.1, -0.4, 0.7], "ypr": [0.0, 0.0, 0.0]}
bot.two_arm_hand_pose(left, right, frame=2)
bot.wait_arm_ee_reached(timeout=10.0)
bot.solve_ik(left, right, frame=2)
bot.solve_fk([0.0] * 14)
```

下肢/躯干：

```python
bot.set_quick_mode(0)
bot.leg_joint([0.0, 0.0, 0.0, 0.0])
bot.wait_leg_joint_reached(timeout=10.0)
bot.torso_pose(x=0.0, y=0.0, z=0.1, roll=0.0, pitch=0.0, yaw=0.0)
bot.wait_torso_reached(timeout=10.0)
```

头/手：

```python
bot.head_body_pose(head_yaw=0.2, head_pitch=0.1)
bot.hand_position(left=[0, 0, 0, 0, 0, 0], right=[0, 0, 0, 0, 0, 0])
bot.claw_command({"field_name": value})  # low-level lejuClawCommand passthrough if message exists
```

### 已确认 ROS Topic

这些接口来自当前运行的 `kuavo5w_sim` 容器。

| Topic | Type | 用途 |
|---|---|---|
| `/cmd_vel` | `geometry_msgs/Twist` | 机器人自身坐标系底盘速度 |
| `/cmd_vel_world` | `geometry_msgs/Twist` | 世界坐标系底盘速度 |
| `/cmd_pose` | `geometry_msgs/Twist` | 机器人自身坐标系底盘位姿目标 |
| `/cmd_pose_world` | `geometry_msgs/Twist` | 世界坐标系底盘位姿目标 |
| `/kuavo_arm_traj` | `sensor_msgs/JointState` | 14 维上肢关节 |
| `/mm/two_arm_hand_pose_cmd` | `kuavo_msgs/twoArmHandPoseCmd` | 双臂末端位姿 |
| `/lb_leg_traj` | `sensor_msgs/JointState` | 4 维下肢/轮臂关节 |
| `/cmd_lb_torso_pose` | `geometry_msgs/Twist` | 躯干位姿 |
| `/control_robot_hand_position` | `kuavo_msgs/robotHandPosition` | 灵巧手位置 |
| `/leju_claw_command` | message from `kuavo_msgs` | LejuClaw 低层命令 |
| `/kuavo_head_body_orientation` | `kuavo_msgs/headBodyPose` | 头部/身体姿态 |
| `/mobile_manipulator/lb_mpc_control_mode` | `std_msgs/Int8` in this setup | 当前 MPC 控制模式 |
| `/lb_cmd_pose_reach_time` | `std_msgs/Float32` | 底盘 pose 到达时间 |
| `/lb_arm_joint_reach_time/left` | `std_msgs/Float32` | 左臂关节到达时间 |
| `/lb_arm_joint_reach_time/right` | `std_msgs/Float32` | 右臂关节到达时间 |
| `/lb_arm_ee_reach_time/left` | `std_msgs/Float32` | 左臂末端到达时间 |
| `/lb_arm_ee_reach_time/right` | `std_msgs/Float32` | 右臂末端到达时间 |
| `/lb_leg_joint_reach_time` | `std_msgs/Float32` | 下肢关节到达时间 |
| `/lb_torso_pose_reach_time` | `std_msgs/Float32` | 躯干到达时间 |

### 已确认 ROS Service

| Service | Type | Args | 用途 |
|---|---|---|---|
| `/mobile_manipulator_mpc_control` | `kuavo_msgs/changeTorsoCtrlMode` | `control_mode` | 主控制模式 |
| `/mobile_manipulator_get_mpc_control_mode` | service from Kuavo | none/varies | 查询主模式 |
| `/mobile_manipulator_mpc_pause_resume` | `ocs2_msgs/pause_resume` | `pause` | 暂停/恢复 MPC |
| `/mobile_manipulator_mpc_reset` | service from Kuavo | varies | MPC reset |
| `/enable_lb_arm_quick_mode` | `kuavo_msgs/changeLbQuickModeSrv` | `quickMode` | quick mode |
| `/wheel_arm_change_arm_ctrl_mode` | `kuavo_msgs/changeArmCtrlMode` | `control_mode` | 5-W 臂控制模式 |
| `/change_arm_ctrl_mode` | `kuavo_msgs/changeArmCtrlMode` | `control_mode` | 臂控制模式 |
| `/humanoid_get_arm_ctrl_mode` | `kuavo_msgs/changeArmCtrlMode` | `control_mode` | 获取/处理臂模式 |
| `/ik/two_arm_hand_pose_cmd_srv` | `kuavo_msgs/twoArmHandPoseCmdSrv` | `twoArmHandPoseCmdRequest` | 双臂 IK |
| `/ik/fk_srv` | `kuavo_msgs/fkSrv` | `q` | 双臂 FK |
| `/execute_arm_action` | `humanoid_plan_arm_trajectory/ExecuteArmAction` | `action_name` | 执行预设动作 |

### 关键消息字段

`geometry_msgs/Twist`：

```text
linear.x, linear.y, linear.z
angular.x, angular.y, angular.z
```

`sensor_msgs/JointState`：

```text
header.stamp
name[]
position[]
velocity[]
effort[]
```

`kuavo_msgs/twoArmHandPoseCmd`：

```text
hand_poses.header
hand_poses.left_pose.pos_xyz[3]
hand_poses.left_pose.quat_xyzw[4]
hand_poses.left_pose.elbow_pos_xyz[3]
hand_poses.left_pose.joint_angles[7]
hand_poses.right_pose.pos_xyz[3]
hand_poses.right_pose.quat_xyzw[4]
hand_poses.right_pose.elbow_pos_xyz[3]
hand_poses.right_pose.joint_angles[7]
use_custom_ik_param
joint_angles_as_q0
ik_param
frame
```

`kuavo_msgs/robotHandPosition`：

```text
header
left_hand_position uint8[]
right_hand_position uint8[]
```

`kuavo_msgs/headBodyPose`：

```text
head_pitch
head_yaw
body_roll
body_pitch
body_yaw
body_x
body_y
body_height
```

`kuavo_msgs/changeTorsoCtrlMode`：

```text
request:  int32 control_mode
response: bool result, int32 mode, string message
```

`kuavo_msgs/changeLbQuickModeSrv`：

```text
request:  int8 quickMode
response: bool success, string message
```

`kuavo_msgs/changeArmCtrlMode`：

```text
request:  int32 control_mode
response: bool result, int32 mode, string message
```

### 控制模式值

主控制模式：

```text
0 NoControl
1 ArmOnly
2 BaseOnly
3 BaseArm
4 ArmEeOnly
```

5-W 臂控制模式：

```text
0 keep current control position
1 reset arm to initial target
2 external controller
```

Quick mode：

```text
0 off
1 lower-body quick
2 arm quick
3 lower-body + arm quick
```

### 接口探测

当前容器里直接运行：

```bash
cd /root/kuavo_deploy
python3 kuavo_sim_platform/scripts/inspect_interfaces.py
```

手动命令：

```bash
source /root/kuavo_ws/installed/setup.bash
source /root/kuavo_ws/devel/setup.bash
rostopic list
rosservice list
rostopic info /cmd_vel
rosservice info /mobile_manipulator_mpc_control
rosmsg show kuavo_msgs/twoArmHandPoseCmd
rossrv show kuavo_msgs/changeTorsoCtrlMode
```

### 官方示例索引

5-W 官方脚本：

```text
cmd_vel_base_test.py
cmd_vel_world_test.py
cmd_pos_base_test.py
cmd_pos_world_test.py
cmd_arm_joint_test.py
cmd_arm_ee_local_test.py
cmd_arm_ee_world_test.py
cmd_arm_ee_joint_test.py
cmd_leg_joint_test.py
cmd_leg_joint_quick_test.py
cmd_torso_pose_test.py
cmd_offline_traj_test.py
check_target_pose_reachable_and_execution.py
timedCmd_example/
armContactForce/
```

官方 SDK atomic examples：

```text
robot_info_example.py
motion_example.py
cmd_pose_example.py
ctrl_arm_example.py
ctrl_arm_example_protected.py
arm_ik_example.py
ctrl_head_example.py
dexhand_example.py
dexhand_state_example.py
lejuclaw_example.py
ctrl_hand_wrench_example.py
wheel_arm_control_example.py
step_control_example.py
observation_example.py
tools_robot_example.py
vision_robot_example.py
controller_example.py
```

### 安全要求

- 第一次测试新脚本时，底盘速度建议不超过 `x=0.05`，持续时间不超过 `1.0` 秒。
- 每段底盘运动后调用 `stop_base()`。
- 脚本结束前调用 `set_mode_no_control()` 或官方 SDK 对应的安全停止/站立接口。
- 第一次测试手臂、躯干、下肢、头部和手时，先用小幅度或零位命令。
- 不要在脚本中无限循环；必须循环时加入退出条件和 `sleep`。
- 不要修改系统文件、源码目录、历史数据、备份目录或虚拟环境。
- 实物机器人运行前必须确认末端执行器类型、周围空间、急停和人员安全。

### 本次脚本问题总结

`left_ok_gesture.py` 调试过程中暴露了几个容易踩坑的问题，后续写脚本时按下面规则处理。

### 1. 5-W 手臂关节值是角度，不是弧度

当前官方 5-W 示例和桌面工具动作帧对 `/kuavo_arm_traj` 的 `sensor_msgs/JointState.position` 使用角度值，例如：

```python
[-30.0, 20.0, 15.0, -45.0, 25.0, 10.0, -35.0]
```

不要按弧度写成：

```python
[1.45, 0.35, 0.85, 1.05]
```

这会小一个数量级，看起来只会轻微闪动。写 5-W `/kuavo_arm_traj` 脚本时，优先参考官方 `cmd_arm_joint_test.py` 或桌面工具导出的角度量级。

### 2. `/kuavo_arm_traj` 14 维顺序不能猜

这次 `make_heart.py` 最大的问题不是数值本身，而是把关节语义猜错了。桌面工具里每条手臂的 7 维顺序是：

```text
arm_pitch
arm_roll
arm_yaw
forearm
hand_yaw
hand_roll
hand_pitch
```

因此 `/kuavo_arm_traj` 的 14 维应按下面理解：

```text
left  = [l_arm_pitch, l_arm_roll, l_arm_yaw, l_forearm, l_hand_yaw, l_hand_roll, l_hand_pitch]
right = [r_arm_pitch, r_arm_roll, r_arm_yaw, r_forearm, r_hand_yaw, r_hand_roll, r_hand_pitch]
arms14 = left + right
```

不要写成：

```text
[shoulder_pitch, shoulder_yaw, shoulder_roll, elbow, wrist_roll, wrist_pitch, wrist_yaw]
```

这个错误会把 roll/yaw、hand_yaw/hand_roll/hand_pitch 全部错位，表现就是：手能动，但动作形状完全不对，甚至绕到背后。

桌面工具示例中右臂能上举的一帧类似：

```text
r_arm_pitch = -179.6
r_arm_roll = -39.9
r_arm_yaw = 90.0
r_forearm = -80.9
r_hand_yaw = -90.0
r_hand_roll = 56.0
r_hand_pitch = 0.0
```

这说明头顶姿态不是完全不可达；之前失败主要是脚本语义错位和末端 IK 分支问题。

### 3. 桌面工具 `.tact` / `standard-action.json` 是 29 维动作帧

桌面工具导出的 `standard-action.json` 和 `.tact` 中 `servos` 不是“全都是手臂”。当前观察到的 29 维顺序应按分区理解：

```text
0..6    left arm 7
7..13   right arm 7
14..19  left hand 6
20..25  right hand 6
26..27  head 2
28      waist 1
```

手部 6 维来自桌面工具 RightHand/LeftHand 页面：

```text
thumb_distal_pitch
thumb_proximal_yaw
index_proximal_finger
middle_proximal_finger
ring_proximal_finger
pinky_proximal_finger
```

范围通常是 `0..100`。脚本里用 `bot.hand_position(left=[...], right=[...])` 控制时，按这 6 维传入。

头部 2 维来自 Head 页面：

```text
head_yaw   [-90, 90]
head_pitch [-20, 45]
```

腰部 1 维来自 Waist 页面：

```text
waist [-180, 180]
```

当前 `KuavoSim` 封装已经有手部接口，但头部/腰部是否需要单独 topic/service，要先用接口检查脚本确认，不能把 29 维直接全部塞进 `/kuavo_arm_traj`。

### 4. 必须切到上肢外部控制模式

只调用主模式 `ArmOnly` 不够。发布 `/kuavo_arm_traj` 前还需要：

```python
bot.set_mode_arm_only()
bot.set_arm_control_mode(2)
```

官方 `lb_ctrl_api.py` 中 `set_arm_control_mode(2)` 的含义是使用外部控制器。缺这一步时，手臂 topic 可能不会被当前控制链路接管。

### 5. 官方 SDK 当前不一定能直接 import

当前容器里源码存在：

```text
/root/kuavo_ws/src/kuavo_humanoid_sdk
```

但调试时发现它不是完整可用的安装状态，遇到过：

```text
ModuleNotFoundError: No module named 'kuavo_humanoid_sdk'
ModuleNotFoundError: No module named 'transitions'
ModuleNotFoundError: No module named 'kuavo_humanoid_sdk.msg.kuavo_msgs'
```

所以脚本不要默认依赖官方 SDK 一定可用。优先使用本项目 `KuavoSim` 封装或直接发 ROS topic/service。确实要用官方 SDK 时，先用一个小脚本验证：

```python
from kuavo_humanoid_sdk import KuavoSDK
print(KuavoSDK().Init())
```

### 6. PYTHONPATH 不能覆盖 ROS 路径

导入脚本运行时需要同时保留：

```text
/root/kuavo_ws/src/kuavo_humanoid_sdk
/root/kuavo_ws/devel/lib/python3/dist-packages
/root/kuavo_ws/installed/lib/python3/dist-packages
/opt/ros/noetic/lib/python3/dist-packages
```

如果只设置：

```bash
PYTHONPATH=/root/kuavo_ws/src/kuavo_humanoid_sdk
```

会导致 `geometry_msgs`、`sensor_msgs`、`kuavo_msgs` 等 ROS Python 包找不到。

### 7. 手部命令单发可能看起来像闪一下

`/control_robot_hand_position` 不是 latched topic。只发布一次手势位置时，仿真里可能看起来只闪一下。建议持续发布一段时间：

```python
def hold_hand_position(bot, seconds, left, right, rate_hz=10):
    interval = 1.0 / float(rate_hz)
    end = time.time() + float(seconds)
    while time.time() < end:
        bot.hand_position(left=left, right=right)
        time.sleep(interval)
```

### 8. “运行后等一会才动”通常不是网页卡

旧路径每次会经过：

```text
检查 Docker / image / container
检查或启动 MuJoCo
等待 ROS ready
运行脚本
```

现在网页“运行脚本”默认使用 `script_fast` 快速路径，只检查 ROS 是否 ready 后直接运行脚本。若仿真休眠或 ROS master 不通，`script_fast` 会快速失败并提示先点击“启动 / 连接”，不会继续执行脚本。

若 ROS 已 ready 但仍然等待较久，通常是脚本内部在等待：

```python
bot.wait_ready()
bot.wait_arm_joint_reached()
time.sleep(DISPLAY_SECONDS)
```

需要更快响应时，减少脚本内部等待，不要盲目修改网页。

### 9. 末端 IK 成功不等于动作合理

`make_heart.py` 调试中验证过：`solve_ik()` 可以很快返回，但末端控制 `/mm/two_arm_hand_pose_cmd` 仍可能出现：

- 手臂绕到背后；
- 手一直在下面；
- 视觉姿态和目标想象完全不一致；
- 每个航点等待 reach-time 导致脚本像卡住。

原因是头顶动作靠近工作空间边界，IK 有多个分支；服务返回“有解”只表示数学上有一个解，不保证是人希望的肘部方向、腕部方向或避碰姿态。

需要精确复现桌面工具姿态时，优先用 `/kuavo_arm_traj` 关节空间；需要空间位置时，再谨慎使用 IK，并提供 elbow hint / q0 / collision 检查。

### 10. 不要把 reach-time 当成可靠节拍器

`/lb_arm_ee_reach_time/*` 和 `/lb_arm_joint_reach_time/*` 在仿真里不一定每条命令都刷新。脚本如果每个航点都：

```python
bot.wait_arm_ee_reached(timeout=6.0)
```

会表现为“运行很久才动”或“像卡住”。连续动作默认应使用固定 `sleep` 控制节拍，只在调试时开启短超时等待。

### 11. 如果 `/kuavo_arm_traj` 不明显，换官方 frame=5 路径

如果角度值已经按官方量级写，仍然看不到明显手臂动作，下一步不要继续乱调数值。改用官方 `cmd_arm_ee_joint_test.py` 中的方式：

```text
/mm/two_arm_hand_pose_cmd
frame = 5
joint_angles_as_q0 = True
```

这条路径是双臂末端命令里的关节空间模式，和 `/kuavo_arm_traj` 是不同控制入口。

### 12. 导入脚本要看版本信息

网页导入脚本后，脚本列表会显示：

```text
filename.py · sha256_short · mtime
```

导入结果会显示：

```text
state: created / updated / unchanged
changed: true / false
sha256: ...
```

如果同内容重新导入，状态应是 `unchanged`，mtime 不会刷新。判断“重新导入是否成功”，不要只看文件名，要看 `state`、`sha256` 和 `mtime`。

### 网页导入流程

1. 打开 Kuavo 5-W 控制台。
2. 操作前确认没有其他协作者正在控制仿真。
3. 在“导入脚本”区域选择 `.py` 文件。
4. 点击“导入脚本”。
5. 在脚本下拉框中选择刚导入的脚本。
6. 点击“运行脚本”。
7. 在右侧输出区域查看运行日志和退出状态。
8. 控制结束后在协作群或当前沟通渠道说明已结束。

### 多人控制协调

Web 控制台不再要求 token。B/C 可以直接通过页面执行以下动作：

- 启动 / 连接。
- 安全探测。
- 前进 Demo。
- 复原 / 停止。
- 暂停 / 恢复 MPC。
- 休眠仿真。
- 运行 YAML 场景。
- 导入 Python 脚本。
- 运行 Python 脚本。

后端仍会串行执行控制命令；如果已有控制命令正在运行，新的请求会被拒绝并提示已有命令在执行。多人协作时需要人工约定当前操作者，一人控制时其他人只观察状态和日志。

### 常见错误

`script name must be an ASCII .py filename`

脚本文件名不符合要求。改成类似：

```text
base_probe_safe.py
```

`unknown script`

网页请求运行的脚本不在导入目录中。重新导入脚本后再运行。

`ROS interfaces were not ready`

仿真或 ROS 接口未就绪。先点击“启动 / 连接”，或查看日志确认 MuJoCo/ROS 是否启动成功。

`Init KuavoSDK failed`

官方 SDK 初始化失败。确认仿真/机器人已经启动，并且脚本在 sourced Kuavo 容器环境中运行。
