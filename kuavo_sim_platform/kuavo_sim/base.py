"""Base velocity control for Kuavo 5-W."""

import time


DEFAULT_LIMITS = {
    "max_vx": 0.30,
    "max_vy": 0.30,
    "max_wyaw": 0.50,
}


def _clamp(name, value, limit, log):
    value = float(value)
    if value > limit:
        log.warn("%s %.3f exceeds %.3f; clamped", name, value, limit)
        return limit
    if value < -limit:
        log.warn("%s %.3f below -%.3f; clamped", name, value, limit)
        return -limit
    return value


class BaseControl:
    CMD_VEL = "/cmd_vel"
    CMD_VEL_WORLD = "/cmd_vel_world"
    CMD_POSE = "/cmd_pose"
    CMD_POSE_WORLD = "/cmd_pose_world"

    def __init__(self, rospy, twist_cls, log, limits=None):
        self.rospy = rospy
        self.twist_cls = twist_cls
        self.log = log
        self.limits = dict(DEFAULT_LIMITS)
        if limits:
            self.limits.update(limits)
        self.pub_vel = rospy.Publisher(self.CMD_VEL, twist_cls, queue_size=10)
        self.pub_vel_world = rospy.Publisher(
            self.CMD_VEL_WORLD, twist_cls, queue_size=10
        )
        self.pub_pose = rospy.Publisher(self.CMD_POSE, twist_cls, queue_size=10)
        self.pub_pose_world = rospy.Publisher(
            self.CMD_POSE_WORLD, twist_cls, queue_size=10
        )

    def wait_cmd_vel_subscriber(self, timeout=10.0):
        end = time.time() + float(timeout)
        rate = self.rospy.Rate(20)
        while time.time() < end and not self.rospy.is_shutdown():
            if self.pub_vel.get_num_connections() > 0:
                return True
            rate.sleep()
        return self.pub_vel.get_num_connections() > 0

    def _velocity_msg(self, x=0.0, y=0.0, yaw=0.0):
        msg = self.twist_cls()
        msg.linear.x = _clamp("vx", x, self.limits["max_vx"], self.log)
        msg.linear.y = _clamp("vy", y, self.limits["max_vy"], self.log)
        msg.linear.z = 0.0
        msg.angular.x = 0.0
        msg.angular.y = 0.0
        msg.angular.z = _clamp("wyaw", yaw, self.limits["max_wyaw"], self.log)
        return msg

    def cmd_vel(self, x=0.0, y=0.0, yaw=0.0):
        self.pub_vel.publish(self._velocity_msg(x=x, y=y, yaw=yaw))

    def cmd_vel_world(self, x=0.0, y=0.0, yaw=0.0):
        self.pub_vel_world.publish(self._velocity_msg(x=x, y=y, yaw=yaw))

    def _pose_msg(self, x=0.0, y=0.0, z=0.0, roll=0.0, pitch=0.0, yaw=0.0):
        msg = self.twist_cls()
        msg.linear.x = float(x)
        msg.linear.y = float(y)
        msg.linear.z = float(z)
        msg.angular.x = float(roll)
        msg.angular.y = float(pitch)
        msg.angular.z = float(yaw)
        return msg

    def cmd_pose(self, x=0.0, y=0.0, yaw=0.0, z=0.0, roll=0.0, pitch=0.0):
        self.pub_pose.publish(
            self._pose_msg(x=x, y=y, z=z, roll=roll, pitch=pitch, yaw=yaw)
        )

    def cmd_pose_world(self, x=0.0, y=0.0, yaw=0.0, z=0.0, roll=0.0, pitch=0.0):
        self.pub_pose_world.publish(
            self._pose_msg(x=x, y=y, z=z, roll=roll, pitch=pitch, yaw=yaw)
        )

    def move_for(self, duration, x=0.0, y=0.0, yaw=0.0, rate=20, world=False):
        publish = self.cmd_vel_world if world else self.cmd_vel
        loop = self.rospy.Rate(float(rate))
        end = time.time() + float(duration)
        while time.time() < end and not self.rospy.is_shutdown():
            publish(x=x, y=y, yaw=yaw)
            loop.sleep()
        self.stop_base(world=world)

    def move_world_for(self, duration, x=0.0, y=0.0, yaw=0.0, rate=20):
        self.move_for(duration, x=x, y=y, yaw=yaw, rate=rate, world=True)

    def stop_base(self, world=False, hold=0.3, rate=20):
        publish = self.cmd_vel_world if world else self.cmd_vel
        loop = self.rospy.Rate(float(rate))
        end = time.time() + float(hold)
        while time.time() < end and not self.rospy.is_shutdown():
            publish(x=0.0, y=0.0, yaw=0.0)
            loop.sleep()
