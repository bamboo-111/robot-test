"""Lower-body and torso control helpers for Kuavo 5-W."""


def _require_len(name, values, expected):
    values = list(values)
    if len(values) != expected:
        raise ValueError(f"{name} requires {expected} values, got {len(values)}")
    return values


class LowerBodyControl:
    LEG_TRAJ = "/lb_leg_traj"
    TORSO_POSE = "/cmd_lb_torso_pose"
    QUICK_MODE_SERVICE = "/enable_lb_arm_quick_mode"

    def __init__(self, rospy, joint_state_cls, twist_cls, kuavo_srv, log):
        self.rospy = rospy
        self.joint_state_cls = joint_state_cls
        self.twist_cls = twist_cls
        self.srv = kuavo_srv
        self.log = log
        self.pub_leg = rospy.Publisher(self.LEG_TRAJ, joint_state_cls, queue_size=10)
        self.pub_torso = rospy.Publisher(self.TORSO_POSE, twist_cls, queue_size=10)

    def leg_joint(self, joints):
        joints = _require_len("leg_joint", joints, 4)
        msg = self.joint_state_cls()
        msg.header.stamp = self.rospy.Time.now()
        msg.position = [float(value) for value in joints]
        self.pub_leg.publish(msg)

    def torso_pose(self, x=0.0, y=0.0, z=0.0, roll=0.0, pitch=0.0, yaw=0.0):
        msg = self.twist_cls()
        msg.linear.x = float(x)
        msg.linear.y = float(y)
        msg.linear.z = float(z)
        msg.angular.x = float(roll)
        msg.angular.y = float(pitch)
        msg.angular.z = float(yaw)
        self.pub_torso.publish(msg)

    def set_quick_mode(self, mode, timeout=5.0):
        self.rospy.wait_for_service(self.QUICK_MODE_SERVICE, timeout=timeout)
        client = self.rospy.ServiceProxy(
            self.QUICK_MODE_SERVICE, self.srv.changeLbQuickModeSrv
        )
        response = client(quickMode=int(mode))
        if not getattr(response, "success", False):
            raise RuntimeError(getattr(response, "message", "quick mode switch failed"))
        return response
