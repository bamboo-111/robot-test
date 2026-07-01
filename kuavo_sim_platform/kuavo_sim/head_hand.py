"""Head and hand topic helpers for Kuavo scripts."""


class HeadHandControl:
    HEAD_BODY = "/kuavo_head_body_orientation"
    ROBOT_HAND = "/control_robot_hand_position"
    LEJU_CLAW = "/leju_claw_command"

    def __init__(self, rospy, kuavo_msg, log):
        self.rospy = rospy
        self.msg = kuavo_msg
        self.log = log
        self.pub_head = rospy.Publisher(
            self.HEAD_BODY, kuavo_msg.headBodyPose, queue_size=10
        )
        self.pub_hand = rospy.Publisher(
            self.ROBOT_HAND, kuavo_msg.robotHandPosition, queue_size=10
        )
        leju_claw_cls = getattr(kuavo_msg, "lejuClawCommand", None)
        self.pub_claw = (
            rospy.Publisher(self.LEJU_CLAW, leju_claw_cls, queue_size=10)
            if leju_claw_cls is not None
            else None
        )

    def head_body_pose(
        self,
        head_pitch=0.0,
        head_yaw=0.0,
        body_roll=0.0,
        body_pitch=0.0,
        body_yaw=0.0,
        body_x=0.0,
        body_y=0.0,
        body_height=0.0,
    ):
        msg = self.msg.headBodyPose()
        msg.head_pitch = float(head_pitch)
        msg.head_yaw = float(head_yaw)
        msg.body_roll = float(body_roll)
        msg.body_pitch = float(body_pitch)
        msg.body_yaw = float(body_yaw)
        msg.body_x = float(body_x)
        msg.body_y = float(body_y)
        msg.body_height = float(body_height)
        self.pub_head.publish(msg)

    def hand_position(self, left=None, right=None):
        msg = self.msg.robotHandPosition()
        msg.header.stamp = self.rospy.Time.now()
        msg.left_hand_position = [int(value) for value in (left or [])]
        msg.right_hand_position = [int(value) for value in (right or [])]
        self.pub_hand.publish(msg)

    def claw_command(self, data):
        if self.pub_claw is None:
            raise RuntimeError("kuavo_msgs/lejuClawCommand is unavailable")
        msg = self.msg.lejuClawCommand()
        for name, value in dict(data).items():
            if not hasattr(msg, name):
                raise ValueError(f"lejuClawCommand has no field: {name}")
            setattr(msg, name, value)
        self.pub_claw.publish(msg)
