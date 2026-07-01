#!/usr/bin/env python3
"""Translate kuavo-5w-test2 desktop action into a runnable KuavoSim script.

Source project:
  E:/project/kuavo/kuavo-5w-test2.kuavoPrj.tar

The desktop project contains one standard action named "salute" with one
keyframe. The exported frame has 29 servo values, but the current local
KuavoSim wrapper exposes the upper-arm joint interface as 14 values through
/kuavo_arm_traj. This script applies the first 14 exported values as the
upper-arm pose and keeps the full raw servo frame below for future mapping.
"""

import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from kuavo_sim import KuavoSim


ACTION_NAME = "salute"
KEYFRAME = 262

# Raw 29-channel servo frame exported by the desktop tool.
RAW_SERVOS = [
    5.2, 0.0, 0.0, -15.5, 0.0, 0.0, 0.0,
    -180.0, -91.3, 90.0, -140.2, -90.0, 5.1, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 100.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
]

# Current KuavoSim /kuavo_arm_traj expects 14 upper-arm joint angles in
# degree-scale values. The desktop tool labels each 7-DOF arm as:
#   [arm_pitch, arm_roll, arm_yaw, forearm,
#    hand_yaw, hand_roll, hand_pitch]
# The exported 29-channel frame is:
#   left arm 7, right arm 7, left hand 6, right hand 6, head 2, waist 1.
ARM_JOINTS = RAW_SERVOS[:14]
ZERO_ARM_JOINTS = [0.0] * 14

HOLD_SECONDS = 5.0
SETTLE_SECONDS = 0.25
RESET_SECONDS = 0.8


def _publish_arm_joint(bot, joints, hold_seconds=0.0, wait_reach=False):
    since = time.time()
    bot.arm_joint(joints)
    if wait_reach:
        reached = bot.wait_arm_joint_reached(timeout=1.0, since=since)
        if reached is None:
            print("[desktop_salute] wait_arm_joint_reached timeout, continue", flush=True)
    if hold_seconds > 0:
        time.sleep(float(hold_seconds))


def main():
    print("[desktop_salute] action=%s keyframe=%s" % (ACTION_NAME, KEYFRAME), flush=True)
    print("[desktop_salute] arm joints=%s" % ARM_JOINTS, flush=True)
    print("[desktop_salute] raw servo channels=%d" % len(RAW_SERVOS), flush=True)

    with KuavoSim() as bot:
        bot.wait_ready(timeout=30.0)

        try:
            bot.set_mode_arm_only()
            bot.set_arm_control_mode(2)
            time.sleep(SETTLE_SECONDS)

            _publish_arm_joint(bot, ARM_JOINTS, hold_seconds=HOLD_SECONDS)
            print("[desktop_salute] action finished", flush=True)
        finally:
            try:
                _publish_arm_joint(bot, ZERO_ARM_JOINTS, hold_seconds=RESET_SECONDS)
                print("[desktop_salute] arm reset finished", flush=True)
            except Exception as exc:
                print("[desktop_salute] arm reset failed: %s" % exc, flush=True)
            try:
                bot.set_mode_no_control()
                print("[desktop_salute] switched to NoControl", flush=True)
            except Exception as exc:
                print("[desktop_salute] set_mode_no_control failed: %s" % exc, flush=True)


if __name__ == "__main__":
    main()
