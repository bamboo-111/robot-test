# Web Episode 操作指南

通过 Web 控制台运行白名单实验、查看 episode 结果和 artifact。

## 1. 打开 Web 控制台

在 Windows PowerShell 中启动：

```powershell
cd E:\project\kuavo
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\windows\start-kuavo5w-web-control.ps1 -Port 8765
```

打开 `http://127.0.0.1:8765/`。

## 2. 运行 fast_health_check

fast_health_check 是一个轻量健康检查，不依赖 ROS master，适合日常快速验证：

1. Web 控制台 → **Episode 管理** → **运行实验**
2. 选择 `fast_health_check`
3. operator 填入你的标识（如 `C`）
4. 点击 **运行实验**
5. 等待完成，右侧输出面板会显示 run_id 和执行结果

## 3. 运行 read_only_interfaces

read_only_interfaces 检查 ROS 接口可用性，需要容器运行：

1. 确保已启动/连接 GUI 仿真
2. 选择 `read_only_interfaces`
3. 点击运行

## 4. 查看最近 episode

**Episode 管理** → **最近 Episodes** 自动显示最近 20 个 episode。

每条记录显示：
- run_id（唯一标识）
- task_name（任务名称）
- ok（成功/失败）
- duration（耗时）
- operator（操作者）
- safe_stop_ok（安全停止状态）
- ⏱ 标记（external_timing 可用）

点击任一 episode 可查看详情。

## 5. 查看 metrics / latency / stdout / stderr

在 episode 详情页，点击 artifact 链接：

| Artifact | 说明 |
|---|---|
| `metrics.json` | 运行指标、成功/失败、耗时 |
| `latency_breakdown.json` | 各阶段耗时分解 |
| `external_timing.json` | 外部时序标记 |
| `stdout.log` | 标准输出 |
| `stderr.log` | 标准错误 |
| `result.json` | 运行结果摘要 |
| `events.jsonl` | 事件时间线 |
| `manifest.json` | episode 清单 |

## 6. 如何反馈失败

如果 episode 失败：

1. 点击失败的 episode
2. 查看 `stderr.log` 和 `result.json`
3. 将 run_id、失败信息、截图反馈给 A

## 7. 安全红线

以下操作 **B/C 不能** 通过 Web 或其他方式执行：

- ❌ **不自动运行 base_probe** — 需要 A 明确确认
- ❌ **不调用 restore** — 复原操作由 A 控制
- ❌ **不运行 move_for** — 任何底盘运动
- ❌ **不执行任意 Python** 作为默认实验入口 — 只能通过白名单实验
- ❌ **不修改 /cmd_vel** — 不直接控制速度指令
- ❌ **不绕过 episode runner** — 所有实验必须通过 episode runner

所有运动任务由 **A** 确认后再执行。

## 8. 可用实验白名单

| 实验 | 说明 | B/C 可用 |
|---|---|---|
| `fast_health_check` | 轻量健康检查，不依赖 ROS | ✅ |
| `read_only_interfaces` | ROS 接口检查 | ✅ |
| `full_interfaces_check` | 完整 ROS 接口检查 | ✅ |
| `base_probe` | 底盘安全探测 | ❌ 需 A 确认 |
