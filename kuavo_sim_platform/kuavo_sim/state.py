"""Runtime state monitoring for Kuavo 5-W."""

import time
from threading import Lock


class StateMonitor:
    MODE_TOPIC = "/mobile_manipulator/lb_mpc_control_mode"
    OBS_TOPIC = "/mobile_manipulator_mpc_observation"
    REACH_TOPICS = {
        "pose": "/lb_cmd_pose_reach_time",
        "arm_joint_left": "/lb_arm_joint_reach_time/left",
        "arm_joint_right": "/lb_arm_joint_reach_time/right",
        "arm_ee_left": "/lb_arm_ee_reach_time/left",
        "arm_ee_right": "/lb_arm_ee_reach_time/right",
        "leg_joint": "/lb_leg_joint_reach_time",
        "torso_pose": "/lb_torso_pose_reach_time",
    }

    def __init__(self, rospy, mode_msg_cls, float_msg_cls, log):
        self.rospy = rospy
        self.log = log
        self._lock = Lock()
        self._mode = None
        self._mode_stamp = 0.0
        self._obs_count = 0
        self._obs_stamp = 0.0
        self._reach = {}
        self._reach_stamp = {}
        self._sub_mode = rospy.Subscriber(
            self.MODE_TOPIC, mode_msg_cls, self._on_mode, queue_size=1
        )
        self._sub_obs = rospy.Subscriber(
            self.OBS_TOPIC, rospy.AnyMsg, self._on_observation, queue_size=1
        )
        self._sub_reach = [
            rospy.Subscriber(
                topic,
                float_msg_cls,
                self._on_reach,
                callback_args=name,
                queue_size=1,
            )
            for name, topic in self.REACH_TOPICS.items()
        ]

    def _on_mode(self, msg):
        with self._lock:
            self._mode = int(getattr(msg, "data"))
            self._mode_stamp = time.time()

    def _on_observation(self, _msg):
        with self._lock:
            self._obs_count += 1
            self._obs_stamp = time.time()

    def _on_reach(self, msg, name):
        with self._lock:
            self._reach[name] = float(getattr(msg, "data", 0.0))
            self._reach_stamp[name] = time.time()

    def current_mode(self):
        with self._lock:
            return self._mode

    def observation_count(self):
        with self._lock:
            return self._obs_count

    def reach_time(self, name):
        with self._lock:
            return self._reach.get(name)

    def wait_reach_time(self, name, timeout=10.0, since=None):
        since = time.time() if since is None else float(since)
        end = time.time() + float(timeout)
        loop = self.rospy.Rate(20)
        while time.time() < end and not self.rospy.is_shutdown():
            with self._lock:
                stamp = self._reach_stamp.get(name, 0.0)
                value = self._reach.get(name)
            if stamp >= since and value is not None and value > 0.0:
                return value
            loop.sleep()
        return None

    def wait_mode(self, mode, timeout=5.0):
        end = time.time() + float(timeout)
        loop = self.rospy.Rate(20)
        while time.time() < end and not self.rospy.is_shutdown():
            if self.current_mode() == int(mode):
                return True
            loop.sleep()
        return self.current_mode() == int(mode)

    def wait_ready(self, base_control, timeout=30.0):
        end = time.time() + float(timeout)
        start_obs = self.observation_count()
        if not base_control.wait_cmd_vel_subscriber(timeout=min(10.0, float(timeout))):
            self.log.warn("timeout waiting for /cmd_vel subscriber")
            return False
        loop = self.rospy.Rate(20)
        while time.time() < end and not self.rospy.is_shutdown():
            with self._lock:
                got_mode = self._mode is not None
                obs_advanced = self._obs_count - start_obs >= 2
            if got_mode and obs_advanced:
                return True
            loop.sleep()
        self.log.warn(
            "timeout waiting for ready state: mode=%s obs_delta=%d",
            self.current_mode(),
            self.observation_count() - start_obs,
        )
        return False
