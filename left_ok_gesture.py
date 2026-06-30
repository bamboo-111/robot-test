#!/usr/bin/env python3
"""Imported Kuavo script - 抬起左臂后左手比 OK 手势。

左侧：KuavoSim 控制左臂关节抬起；
左手：官方 DexterousHand.make_gesture 输出 "ok" 手势。
两套接口分属不同库，需各自初始化。
"""

import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from kuavo_sim import KuavoSim
from kuavo_humanoid_sdk import KuavoSDK, KuavoRobot, DexterousHand


# 14 维上肢关节零位（弧度）。顺序通常为：
#   左[肩pitch, 肩yaw, 肩roll, 肘, 腕roll, 腕pitch, 腕yaw]
#   右[肩pitch, 肩yaw, 肩roll, 肂, 腕roll, 腕pitch, 腕yaw]
ZERO_POSE = [0.0] * 14


def _left_arm_raised():
    """左臂抬起姿态：左肩 pitch 抬起，肘部适度弯曲，右臂保持零位。"""
    pose = list(ZERO_POSE)
    pose[0] = 1.2     # 左肩 pitch（抬起）
    pose[1] = 0.2     # 左肩 yaw
    pose[2] = 0.6     # 左肩 roll
    pose[3] = 0.8     # 左肘 弯曲
    # 左腕保持零位（让灵巧手露出来，方便做 OK 手势）
    return pose


def main():
    # --- 1) 初始化官方 SDK（DexterousHand 依赖它）---
    if not KuavoSDK().Init():
        raise RuntimeError("Init KuavoSDK failed")
    robot = KuavoRobot()
    hand = DexterousHand()

    with KuavoSim() as bot:
        bot.wait_ready(timeout=30.0)

        # --- 2) 进入纯手臂控制模式 ---
        bot.set_mode_arm_only()
        time.sleep(1.0)

        # --- 3) 先回零位建立基准 ---
        bot.arm_joint(ZERO_POSE)
        bot.wait_arm_joint_reached(timeout=10.0)

        # --- 4) 抬起左臂 ---
        bot.arm_joint(_left_arm_raised())
        bot.wait_arm_joint_reached(timeout=10.0)
        time.sleep(1.0)  # 稳定一下，便于手部做手势

        # --- 5) 左手比 OK 手势（右手不动作，给默认） ---
        hand.make_gesture(l_gesture_name="ok", r_gesture_name="open")
        # make_gesture 为异步命令，保持一会儿让手势完成并展示
        time.sleep(3.0)

        # --- 6) 安全复位 ---
        # 先把手张开，再放下手臂
        hand.open()
        time.sleep(1.0)
        bot.arm_joint(ZERO_POSE)
        bot.wait_arm_joint_reached(timeout=10.0)
        bot.set_mode_no_control()


if __name__ == "__main__":
    main()
