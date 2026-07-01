#!/usr/bin/env python3
"""Small multi-interface development probe for Kuavo 5-W."""

import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from kuavo_sim import KuavoSim


def main():
    with KuavoSim() as bot:
        bot.wait_ready(timeout=30.0)

        bot.set_mode_base_only()
        bot.move_for(duration=0.5, x=0.03, y=0.0, yaw=0.0)
        bot.cmd_pose(x=0.05, y=0.0, yaw=0.0)
        pose_time = bot.wait_pose_reached(timeout=5.0)
        if pose_time:
            bot.rospy.sleep(pose_time + 0.2)
        bot.stop_base()

        bot.head_body_pose(head_yaw=0.2, head_pitch=0.1)
        time.sleep(0.5)
        bot.head_body_pose(head_yaw=0.0, head_pitch=0.0)

        bot.hand_position(left=[0, 0, 0, 0, 0, 0], right=[0, 0, 0, 0, 0, 0])

        bot.set_mode_arm_only()
        bot.set_arm_control_mode(2)
        bot.arm_joint([0.0] * 14)
        arm_time = bot.wait_arm_joint_reached(timeout=5.0)
        if arm_time:
            bot.rospy.sleep(arm_time + 0.2)

        bot.set_mode_no_control()


if __name__ == "__main__":
    main()
