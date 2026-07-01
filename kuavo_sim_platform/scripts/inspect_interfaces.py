#!/usr/bin/env python3
"""Print available Kuavo ROS topics and services for script development."""

import os
import subprocess


TOPICS = [
    "/cmd_vel",
    "/cmd_vel_world",
    "/cmd_pose",
    "/cmd_pose_world",
    "/kuavo_arm_traj",
    "/mm/two_arm_hand_pose_cmd",
    "/lb_leg_traj",
    "/cmd_lb_torso_pose",
    "/control_robot_hand_position",
    "/leju_claw_command",
    "/kuavo_head_body_orientation",
    "/mobile_manipulator/lb_mpc_control_mode",
    "/lb_cmd_pose_reach_time",
    "/lb_arm_joint_reach_time/left",
    "/lb_arm_ee_reach_time/left",
    "/lb_leg_joint_reach_time",
    "/lb_torso_pose_reach_time",
]

SERVICES = [
    "/mobile_manipulator_mpc_control",
    "/mobile_manipulator_get_mpc_control_mode",
    "/mobile_manipulator_mpc_pause_resume",
    "/mobile_manipulator_mpc_reset",
    "/enable_lb_arm_quick_mode",
    "/wheel_arm_change_arm_ctrl_mode",
    "/change_arm_ctrl_mode",
    "/humanoid_get_arm_ctrl_mode",
    "/ik/two_arm_hand_pose_cmd_srv",
    "/ik/fk_srv",
    "/execute_arm_action",
]


def _run(args):
    return subprocess.run(
        args,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
    ).stdout.strip()


def main():
    print("ROS_MASTER_URI=", os.environ.get("ROS_MASTER_URI", ""))
    print("\n# Topics")
    for topic in TOPICS:
        print(f"\n## {topic}")
        print(_run(["rostopic", "info", topic]))
    print("\n# Services")
    for service in SERVICES:
        print(f"\n## {service}")
        print(_run(["rosservice", "info", service]))


if __name__ == "__main__":
    main()
