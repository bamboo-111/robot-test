#!/usr/bin/env python3
"""Imported Kuavo script - 抬起左臂后左手比 OK 手势。

左侧：KuavoSim 控制左臂关节抬起；
左手：直接发布 /control_robot_hand_position 位置命令。
这样不依赖当前容器里尚未完整安装的 kuavo_humanoid_sdk 生成消息包。
"""

import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from kuavo_sim import KuavoSim


# 14 维上肢关节零位。5-W 官方 test_kuavo_wheel_real 示例对
# /kuavo_arm_traj 的 JointState.position 使用角度值，不是弧度。
# 顺序通常为：
#   左[肩pitch, 肩yaw, 肩roll, 肘, 腕roll, 腕pitch, 腕yaw]
#   右[肩pitch, 肩yaw, 肩roll, 肂, 腕roll, 腕pitch, 腕yaw]
ZERO_POSE = [0.0] * 14
OPEN_HAND = [0, 0, 0, 0, 0, 0]
# 6 DOF order from official SDK:
# thumb, thumb_aux, index, middle, ring, pinky.
# "OK" keeps thumb/index more open and folds the remaining fingers.
LEFT_OK_HAND = [10, 10, 15, 100, 100, 100]
DISPLAY_SECONDS = 8.0


def _left_arm_raised():
    """左臂明显展臂姿态，使用官方 5-W 示例同量级的角度值。"""
    pose = list(ZERO_POSE)
    pose[:7] = [-30.0, 20.0, 15.0, -45.0, 25.0, 10.0, -35.0]
    return pose


def _hold_hand_position(bot, seconds, left, right, rate_hz=10):
    interval = 1.0 / float(rate_hz)
    end = time.time() + float(seconds)
    while time.time() < end:
        bot.hand_position(left=left, right=right)
        time.sleep(interval)


def main():
    with KuavoSim() as bot:
        bot.wait_ready(timeout=30.0)

        # --- 2) 进入纯手臂控制模式 ---
        bot.set_mode_arm_only()
        bot.set_arm_control_mode(2)
        time.sleep(1.0)

        # --- 3) 先回零位建立基准 ---
        bot.arm_joint(ZERO_POSE)
        bot.wait_arm_joint_reached(timeout=10.0)

        # --- 4) 抬起左臂 ---
        bot.arm_joint(_left_arm_raised())
        bot.wait_arm_joint_reached(timeout=10.0)
        time.sleep(1.0)  # 稳定一下，便于手部做手势

        # --- 5) 左手比 OK 手势（右手不动作，给默认） ---
        # 手部命令不是 latched topic，持续发布更容易在仿真中稳定显示。
        _hold_hand_position(bot, DISPLAY_SECONDS, left=LEFT_OK_HAND, right=OPEN_HAND)
        time.sleep(1.0)

        # --- 6) 安全复位 ---
        # 先把手张开，再放下手臂
        _hold_hand_position(bot, 1.0, left=OPEN_HAND, right=OPEN_HAND)
        time.sleep(1.0)
        bot.arm_joint(ZERO_POSE)
        bot.wait_arm_joint_reached(timeout=10.0)
        bot.set_mode_no_control()


if __name__ == "__main__":
    main()
