"""Arm and end-effector control helpers for Kuavo 5-W."""

import math


ARM_JOINT_NAMES = [f"joint{i}" for i in range(1, 15)]


def _require_len(name, values, expected):
    values = list(values)
    if len(values) != expected:
        raise ValueError(f"{name} requires {expected} values, got {len(values)}")
    return values


def _quat_from_euler(roll, pitch, yaw):
    cr = math.cos(float(roll) * 0.5)
    sr = math.sin(float(roll) * 0.5)
    cp = math.cos(float(pitch) * 0.5)
    sp = math.sin(float(pitch) * 0.5)
    cy = math.cos(float(yaw) * 0.5)
    sy = math.sin(float(yaw) * 0.5)
    return [
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
        cr * cp * cy + sr * sp * sy,
    ]


class ArmControl:
    ARM_TRAJ = "/kuavo_arm_traj"
    TWO_ARM_EE = "/mm/two_arm_hand_pose_cmd"
    ARM_MODE_SERVICE = "/wheel_arm_change_arm_ctrl_mode"
    IK_SERVICE = "/ik/two_arm_hand_pose_cmd_srv"
    FK_SERVICE = "/ik/fk_srv"
    ACTION_SERVICE = "/execute_arm_action"

    def __init__(self, rospy, joint_state_cls, kuavo_msg, kuavo_srv, log):
        self.rospy = rospy
        self.joint_state_cls = joint_state_cls
        self.msg = kuavo_msg
        self.srv = kuavo_srv
        self.log = log
        self.pub_arm = rospy.Publisher(self.ARM_TRAJ, joint_state_cls, queue_size=10)
        self.pub_ee = rospy.Publisher(
            self.TWO_ARM_EE, kuavo_msg.twoArmHandPoseCmd, queue_size=10
        )

    def arm_joint(self, joints, names=None):
        joints = _require_len("arm_joint", joints, 14)
        msg = self.joint_state_cls()
        msg.header.stamp = self.rospy.Time.now()
        msg.name = list(names) if names is not None else ARM_JOINT_NAMES
        msg.position = [float(value) for value in joints]
        self.pub_arm.publish(msg)

    def _arm_pose(
        self,
        xyz=None,
        quat=None,
        ypr=None,
        elbow_xyz=None,
        joint_angles=None,
    ):
        pose = self.msg.armHandPose()
        pose.pos_xyz = [float(value) for value in _require_len("xyz", xyz or [0, 0, 0], 3)]
        if quat is None:
            if ypr is None:
                quat = [0.0, 0.0, 0.0, 1.0]
            else:
                yaw, pitch, roll = _require_len("ypr", ypr, 3)
                quat = _quat_from_euler(roll, pitch, yaw)
        pose.quat_xyzw = [float(value) for value in _require_len("quat", quat, 4)]
        pose.elbow_pos_xyz = [
            float(value) for value in _require_len("elbow_xyz", elbow_xyz or [0, 0, 0], 3)
        ]
        pose.joint_angles = [
            float(value)
            for value in _require_len("joint_angles", joint_angles or [0] * 7, 7)
        ]
        return pose

    def two_arm_pose_cmd(
        self,
        left,
        right,
        frame=2,
        use_custom_ik_param=False,
        joint_angles_as_q0=False,
    ):
        msg = self.msg.twoArmHandPoseCmd()
        msg.hand_poses = self.msg.twoArmHandPose()
        msg.hand_poses.header.stamp = self.rospy.Time.now()
        msg.hand_poses.header.frame_id = "base_link"
        msg.hand_poses.left_pose = self._arm_pose(**left)
        msg.hand_poses.right_pose = self._arm_pose(**right)
        msg.use_custom_ik_param = bool(use_custom_ik_param)
        msg.joint_angles_as_q0 = bool(joint_angles_as_q0)
        msg.ik_param = self.msg.ikSolveParam()
        msg.frame = int(frame)
        return msg

    def two_arm_hand_pose(self, left, right, frame=2):
        self.pub_ee.publish(self.two_arm_pose_cmd(left=left, right=right, frame=frame))

    def solve_ik(self, left, right, frame=2, timeout=5.0):
        self.rospy.wait_for_service(self.IK_SERVICE, timeout=timeout)
        client = self.rospy.ServiceProxy(self.IK_SERVICE, self.srv.twoArmHandPoseCmdSrv)
        request = self.two_arm_pose_cmd(left=left, right=right, frame=frame)
        return client(twoArmHandPoseCmdRequest=request)

    def solve_fk(self, joints, timeout=5.0):
        self.rospy.wait_for_service(self.FK_SERVICE, timeout=timeout)
        client = self.rospy.ServiceProxy(self.FK_SERVICE, self.srv.fkSrv)
        return client(q=[float(value) for value in joints])

    def set_arm_control_mode(self, mode, timeout=5.0):
        self.rospy.wait_for_service(self.ARM_MODE_SERVICE, timeout=timeout)
        client = self.rospy.ServiceProxy(
            self.ARM_MODE_SERVICE, self.srv.changeArmCtrlMode
        )
        response = client(control_mode=int(mode))
        if not getattr(response, "result", False):
            raise RuntimeError(getattr(response, "message", "arm mode switch failed"))
        return response

    def execute_arm_action(self, action_name, timeout=5.0):
        if not hasattr(self.srv, "ExecuteArmAction"):
            raise RuntimeError("humanoid_plan_arm_trajectory/ExecuteArmAction is unavailable")
        self.rospy.wait_for_service(self.ACTION_SERVICE, timeout=timeout)
        client = self.rospy.ServiceProxy(
            self.ACTION_SERVICE, self.srv.ExecuteArmAction
        )
        return client(action_name=str(action_name))
