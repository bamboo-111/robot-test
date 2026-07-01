#!/usr/bin/env python3
"""Salute-and-cruise: 一个幅度更大、跨多子系统的复合动作。

动作编排（约 22 秒）：
  阶段 A - 备礼:  双臂抬起做敬礼预备姿态，头部转向正前。
  阶段 B - 敬礼:  右臂敬礼保持 2 秒，左手贴身，灵巧手半握。
  阶段 C - 收礼:  双臂展开成"欢迎"姿态，灵巧手张开。
  阶段 D - 巡游:  切 BaseArm，底盘低速前进 2 秒 + 原地左转，双臂保持欢迎姿态，
                   头部随转向左偏。
  阶段 E - 致意挥手: 停车后右臂大幅挥手 3 次。
  阶段 F - 复位:  双臂回中立、手张开、头回正、切回 NoControl。

严格遵循 README 调试经验:
  16.1 /kuavo_arm_traj 用【角度】非弧度。
  16.2 14 维 = left7(arm_pitch,arm_roll,arm_yaw,forearm,hand_yaw,hand_roll,hand_pitch)
              + right7(同序)。
  16.3 发 /kuavo_arm_traj 前必须 set_mode_arm_only() + set_arm_control_mode(2)。
  16.4 连续动作用固定 sleep 节拍，不等 reach-time。
  16.7 /control_robot_hand_position 非 latched，需持续发布。
  安全: 底盘速度守限(move_for 自带 clamp 0.30/0.50)；每段运动后 stop_base；
        退出前 fail_safe(KuavoSim.__exit__ 已内置) + 显式 NoControl。

接口签名已对齐服务器 kuavo_sim 包源码(client.py / arm.py / base.py / head_hand.py):
  arm_joint(joints[14])                      角度
  set_arm_control_mode(mode_int)
  move_for(duration, x, y, yaw, rate=20)
  stop_base(world=False, hold=0.3)
  head_body_pose(head_yaw=, head_pitch=, ...) 度
  hand_position(left=[6], right=[6])          int 0..100
"""

import os
import sys
import time
import math

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from kuavo_sim import KuavoSim  # noqa: E402


# ---------------------------------------------------------------------------
# 每条手臂 7 维（度）。索引语义:
#   0 arm_pitch  1 arm_roll  2 arm_yaw  3 forearm
#   4 hand_yaw   5 hand_roll 6 hand_pitch
# ---------------------------------------------------------------------------

# 中立: 双臂自然下垂贴身
L_NEUTRAL = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
R_NEUTRAL = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

# 敬礼: 右臂抬到太阳穴附近，前臂内收成敬礼角；左手贴身
#   r_arm_pitch 负=向前上抬；r_arm_roll 让上臂内收；r_forearm 弯肘
R_SALUTE = [-110.0, 25.0, 0.0, -120.0, 0.0, 0.0, -10.0]

# 欢迎: 双臂向两侧平展开（大动作），略向前
#   左右对称：roll 一正一负让两臂向两侧打开
L_WELCOME = [-70.0, -40.0, 0.0, -20.0, 0.0, 0.0, 0.0]
R_WELCOME = [-70.0, 40.0, 0.0, -20.0, 0.0, 0.0, 0.0]

# 挥手起点(右臂高举偏外)，挥动时改 hand_yaw
R_WAVE_UP = [-150.0, 35.0, 0.0, -40.0, 0.0, 0.0, 0.0]
R_WAVE_IN = list(R_WAVE_UP); R_WAVE_IN[4] = -45.0   # 手向内
R_WAVE_OUT = list(R_WAVE_UP); R_WAVE_OUT[4] = 45.0  # 手向外

# 灵巧手(6 维 int 0..100): thumb_distal, thumb_proximal_yaw, index, middle, ring, pinky
HAND_OPEN = [0, 0, 0, 0, 0, 0]        # 全张
HAND_HALF = [30, 30, 30, 30, 30, 30]  # 半握(敬礼)
HAND_RELAX = [20, 20, 20, 20, 20, 20]


def arms14(left7, right7):
    assert len(left7) == 7 and len(right7) == 7
    return list(left7) + list(right7)


def ease(t):
    t = max(0.0, min(1.0, t))
    return 0.5 - 0.5 * math.cos(math.pi * t)


def lerp(a, b, t):
    return [x + (y - x) * t for x, y in zip(a, b)]


def transition(bot, l0, r0, l1, r1, seconds, hz=50):
    """关节空间平滑过渡：l0/r0 -> l1/r1，固定节拍发布 /kuavo_arm_traj。"""
    interval = 1.0 / float(hz)
    steps = max(1, int(seconds * hz))
    for i in range(1, steps + 1):
        t = ease(i / steps)
        bot.arm_joint(arms14(lerp(l0, l1, t), lerp(r0, r1, t)))
        time.sleep(interval)
    return list(l1), list(r1)


def hold(bot, left7, right7, seconds, hz=30):
    """持续发布一个手臂姿态 + 半握/张开的手部位置（非 latched，需持续发）。"""
    interval = 1.0 / float(hz)
    end = time.time() + float(seconds)
    while time.time() < end:
        bot.arm_joint(arms14(left7, right7))
        time.sleep(interval)


def hold_with_hand(bot, left7, right7, left_hand, right_hand, seconds, hz=30):
    """同时持续发布手臂姿态和灵巧手位置。"""
    interval = 1.0 / float(hz)
    end = time.time() + float(seconds)
    while time.time() < end:
        bot.arm_joint(arms14(left7, right7))
        bot.hand_position(left=left_hand, right=right_hand)
        time.sleep(interval)


def main():
    with KuavoSim() as bot:
        print("[cruise] 等待 ROS / MPC / 控制接口就绪 ...")
        bot.wait_ready(timeout=30.0)

        cur_l, cur_r = list(L_NEUTRAL), list(R_NEUTRAL)

        # ===== 阶段 A: 备礼 — 抬双臂到敬礼位 =====
        print("[cruise] A. 备礼: 抬臂 + 头转正 ...")
        bot.set_mode_arm_only()
        bot.set_arm_control_mode(2)
        time.sleep(0.4)
        cur_l, cur_r = transition(bot, cur_l, cur_r, L_NEUTRAL, R_SALUTE, seconds=1.6)
        bot.head_body_pose(head_yaw=0.0, head_pitch=0.0)
        hold_with_hand(bot, cur_l, cur_r, HAND_HALF, HAND_HALF, seconds=0.5)

        # ===== 阶段 B: 敬礼保持 =====
        print("[cruise] B. 敬礼保持 2s ...")
        hold_with_hand(bot, cur_l, cur_r, HAND_HALF, HAND_HALF, seconds=2.0)

        # ===== 阶段 C: 收礼 -> 双臂展开"欢迎" =====
        print("[cruise] C. 展开双臂欢迎姿态 ...")
        cur_l, cur_r = transition(bot, cur_l, cur_r, L_WELCOME, R_WELCOME, seconds=1.4)
        hold_with_hand(bot, cur_l, cur_r, HAND_OPEN, HAND_OPEN, seconds=0.8)

        # ===== 阶段 D: 巡游 — 切 BaseArm，低速前进 + 转向 =====
        print("[cruise] D. 切 BaseArm, 低速巡游 ...")
        bot.set_mode_base_arm()
        bot.set_arm_control_mode(2)
        time.sleep(0.5)
        # 重新接管手臂(模式切换后), 保持欢迎姿态
        hold_with_hand(bot, L_WELCOME, R_WELCOME, HAND_OPEN, HAND_OPEN, seconds=0.3)

        # D1: 前进 2s（在 move_for 持续期间，并行维持手臂姿态很难；
        #     这里采用"分段"策略: 短脉冲前进 + 之间补发手臂）
        # 底盘限速 vx<=0.30, wyaw<=0.50，用保守值
        print("[cruise]    D1. 前进 x=0.20, 2.0s ...")
        bot.move_for(duration=2.0, x=0.20, y=0.0, yaw=0.0)
        # move_for 内部会 stop_base；补发一次手臂防止漂移
        bot.arm_joint(arms14(L_WELCOME, R_WELCOME))

        # D2: 原地左转 1.2s，头部跟随左偏
        print("[cruise]    D2. 原地左转 yaw=0.40, 1.2s, 头左偏 ...")
        bot.head_body_pose(head_yaw=-25.0, head_pitch=0.0)
        bot.move_for(duration=1.2, x=0.0, y=0.0, yaw=0.40)
        bot.arm_joint(arms14(L_WELCOME, R_WELCOME))

        # D3: 头回正，停车
        bot.head_body_pose(head_yaw=0.0, head_pitch=0.0)
        bot.stop_base(hold=0.4)

        # ===== 阶段 E: 致意挥手 — 切回 ArmOnly，右臂大幅挥手 3 次 =====
        print("[cruise] E. 切回 ArmOnly, 右臂挥手 3 次 ...")
        bot.set_mode_arm_only()
        bot.set_arm_control_mode(2)
        time.sleep(0.4)
        # 先把右臂从欢迎位移到挥手起点(高举)
        cur_l, cur_r = transition(bot, L_WELCOME, R_WELCOME, L_NEUTRAL, R_WAVE_UP, seconds=1.2)
        hold_with_hand(bot, cur_l, cur_r, HAND_OPEN, HAND_OPEN, seconds=0.2)

        for i in range(3):
            tgt = R_WAVE_OUT if i % 2 == 0 else R_WAVE_IN
            cur_l, cur_r = transition(bot, cur_l, cur_r, L_NEUTRAL, tgt, seconds=0.5)
        # 回到挥手起点
        cur_l, cur_r = transition(bot, cur_l, cur_r, L_NEUTRAL, R_WAVE_UP, seconds=0.5)
        hold_with_hand(bot, cur_l, cur_r, HAND_OPEN, HAND_OPEN, seconds=0.3)

        # ===== 阶段 F: 复位 =====
        print("[cruise] F. 复位: 双臂回中立, 手张开, 头回正 ...")
        cur_l, cur_r = transition(bot, cur_l, cur_r, L_NEUTRAL, R_NEUTRAL, seconds=1.6)
        hold_with_hand(bot, cur_l, cur_r, HAND_OPEN, HAND_OPEN, seconds=0.5)
        bot.head_body_pose(head_yaw=0.0, head_pitch=0.0)

        print("[cruise] 切回 NoControl，结束。")
        bot.set_mode_no_control()

    print("[cruise] done.")


if __name__ == "__main__":
    main()
