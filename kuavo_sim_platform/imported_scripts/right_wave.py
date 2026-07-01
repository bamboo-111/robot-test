#!/usr/bin/env python3
"""Right-arm wave gesture for Kuavo5-W (wheel-arm humanoid).

导入脚本（Web 控制台）。运行前提：MuJoCo / ROS 已就绪，操作者已持锁。

本脚本严格遵循 README 第 16 章调试经验：
  1. /kuavo_arm_traj 的 position 使用【角度】，不是弧度。
  2. 14 维顺序 = left7(arm_pitch..hand_pitch) + right7(...)，不能猜。
  3. 发 /kuavo_arm_traj 前必须先 set_mode_arm_only() + set_arm_control_mode(2)
     (外部控制器)，否则手臂 topic 不会被控制链路接管。
  4. 不把 reach-time 当节拍器，连续动作用固定 sleep 控制节奏。
  5. 安全要求：首次测试用小幅度；退出前复位并切回 NoControl。

姿态语义（每条手臂 7 维，单位：度）：
  index: 0 arm_pitch
         1 arm_roll
         2 arm_yaw
         3 forearm
         4 hand_yaw
         5 hand_roll
         6 hand_pitch
"""

import os
import sys
import time
import math

# 让脚本无论从哪里启动都能找到本项目的 kuavo_sim 包
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from kuavo_sim import KuavoSim  # noqa: E402


# ---------------------------------------------------------------------------
# 姿态定义（角度，degs）。left7/right7 与 /kuavo_arm_traj 的 14 维顺序一致。
# ---------------------------------------------------------------------------

# 安静位姿：双臂自然下垂、贴近身体。
LEFT_NEUTRAL = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
RIGHT_NEUTRAL = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

# 挥手准备位姿：右臂抬起、前臂朝外，手举到肩高偏外。
#   r_arm_pitch 负值=向前/向上抬；
#   r_arm_roll  让整臂略向外；r_arm_yaw 让肘朝向合适方向；
#   r_forearm   控制前臂/肘弯曲角度。
RIGHT_WAVE_READY = [-90.0, -20.0, 0.0, -90.0, 0.0, 0.0, 0.0]

# 挥手两个极限帧：在前臂平面内左右摆动（通过 hand_yaw / forearm 组合实现）。
# 这里让前臂与手部在“内收 / 外展”两个状态间交替。
RIGHT_WAVE_LEFT = list(RIGHT_WAVE_READY)
RIGHT_WAVE_LEFT[4] = -40.0  # hand_yaw 向内

RIGHT_WAVE_RIGHT = list(RIGHT_WAVE_READY)
RIGHT_WAVE_RIGHT[4] = 40.0   # hand_yaw 向外


def to_arms14(left7, right7):
    """拼成 /kuavo_arm_traj 期望的 14 维（left7 + right7）。"""
    assert len(left7) == 7 and len(right7) == 7, "每条手臂必须是 7 维角度"
    return list(left7) + list(right7)


def ease_in_out(t):
    """0..1 的平滑插值，避免关节硬跳。"""
    return 0.5 - 0.5 * math.cos(math.pi * max(0.0, min(1.0, t)))


def lerp(a, b, t):
    return [x + (y - x) * t for x, y in zip(a, b)]


def hold_pose(bot, left7, right7, seconds, rate_hz=50):
    """以固定频率持续发布一个手臂姿态一段时间。

    /kuavo_arm_traj 不是 latched topic，单发一次往往不可靠，
    因此连续段用固定 sleep 节拍持续发布，而不是等 reach-time。
    """
    arms = to_arms14(left7, right7)
    interval = 1.0 / float(rate_hz)
    end = time.time() + float(seconds)
    while time.time() < end:
        bot.arm_joint(arms)
        time.sleep(interval)


def move_to(bot, left_from, right_from, left_to, right_to, seconds, rate_hz=50):
    """在 seconds 内从当前姿态平滑过渡到目标姿态。"""
    interval = 1.0 / float(rate_hz)
    steps = max(1, int(seconds * rate_hz))
    for i in range(1, steps + 1):
        t = ease_in_out(i / steps)
        left = lerp(left_from, left_to, t)
        right = lerp(right_from, right_to, t)
        bot.arm_joint(to_arms14(left, right))
        time.sleep(interval)


def main():
    with KuavoSim() as bot:
        print("[wave] 等待 ROS / MPC / 控制接口就绪 ...")
        bot.wait_ready(timeout=30.0)

        # --- 关键第 3 点：发布 /kuavo_arm_traj 前必须切外部控制器模式 ---
        print("[wave] 切 ArmOnly + 外部手臂控制模式 (mode=2) ...")
        bot.set_mode_arm_only()
        bot.set_arm_control_mode(2)
        time.sleep(0.5)

        # 用局部变量跟踪当前右臂姿态，避免给全局常量赋值（作用域 bug）
        cur_right = list(RIGHT_WAVE_READY)

        # 1) 从中立位平滑抬到挥手准备位（慢，安全）
        print("[wave] 抬起右臂到挥手准备位 ...")
        move_to(bot,
                LEFT_NEUTRAL, RIGHT_NEUTRAL,
                LEFT_NEUTRAL, cur_right,
                seconds=1.5)
        hold_pose(bot, LEFT_NEUTRAL, cur_right, seconds=0.4)

        # 2) 左右摆动若干次（固定节拍，不用 reach-time）
        waves = 3
        print(f"[wave] 挥手 {waves} 次 ...")
        for i in range(waves):
            tgt = list(RIGHT_WAVE_RIGHT) if i % 2 == 0 else list(RIGHT_WAVE_LEFT)
            move_to(bot,
                    LEFT_NEUTRAL, cur_right,
                    LEFT_NEUTRAL, tgt,
                    seconds=0.45)
            cur_right = tgt  # 下一帧从这里出发

        # 3) 回到准备位停留一下
        print("[wave] 回到准备位 ...")
        move_to(bot,
                LEFT_NEUTRAL, cur_right,
                LEFT_NEUTRAL, RIGHT_WAVE_READY,
                seconds=0.5)
        cur_right = list(RIGHT_WAVE_READY)
        hold_pose(bot, LEFT_NEUTRAL, cur_right, seconds=0.3)

        # 4) 平稳放下手臂
        print("[wave] 放下手臂到中立位 ...")
        move_to(bot,
                LEFT_NEUTRAL, cur_right,
                LEFT_NEUTRAL, RIGHT_NEUTRAL,
                seconds=1.5)

        # --- 安全收尾：回中立 + 切回 NoControl ---
        hold_pose(bot, LEFT_NEUTRAL, RIGHT_NEUTRAL, seconds=0.3)
        print("[wave] 切回 NoControl，结束。")
        bot.set_mode_no_control()

    print("[wave] done.")


if __name__ == "__main__":
    main()
