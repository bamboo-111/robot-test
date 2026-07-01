"""High-level Kuavo 5-W ROS client."""

import importlib
import os
import sys

from .base import BaseControl, DEFAULT_LIMITS
from .arm import ArmControl
from .head_hand import HeadHandControl
from .lower_body import LowerBodyControl
from .modes import CtrlMode, resolve_mode
from .state import StateMonitor


DEFAULT_LB_API_DIR = "/root/kuavo_ws/src/demo/test_kuavo_wheel_real"
DEFAULT_MODE_MSG_TYPE = "std_msgs/Int8"


class KuavoSimError(RuntimeError):
    """Raised when a KuavoSim runtime operation cannot complete."""


class _Log:
    def __init__(self, rospy=None):
        self.rospy = rospy

    def info(self, msg, *args):
        if self.rospy:
            self.rospy.loginfo(msg, *args)
        else:
            print(msg % args if args else msg)

    def warn(self, msg, *args):
        if self.rospy:
            self.rospy.logwarn(msg, *args)
        else:
            print("WARNING: " + (msg % args if args else msg))

    def error(self, msg, *args):
        if self.rospy:
            self.rospy.logerr(msg, *args)
        else:
            print("ERROR: " + (msg % args if args else msg))


def _resolve_msg_class(type_name):
    if "/" not in type_name:
        raise KuavoSimError(f"invalid ROS message type: {type_name}")
    package, name = type_name.split("/", 1)
    module = importlib.import_module(f"{package}.msg")
    return getattr(module, name)


def _require_ros():
    try:
        rospy = importlib.import_module("rospy")
        geometry_msg = importlib.import_module("geometry_msgs.msg")
        sensor_msg = importlib.import_module("sensor_msgs.msg")
        std_msg = importlib.import_module("std_msgs.msg")
        kuavo_msg = importlib.import_module("kuavo_msgs.msg")
        kuavo_srv = importlib.import_module("kuavo_msgs.srv")
        try:
            action_srv = importlib.import_module("humanoid_plan_arm_trajectory.srv")
            if not hasattr(kuavo_srv, "ExecuteArmAction"):
                setattr(kuavo_srv, "ExecuteArmAction", action_srv.ExecuteArmAction)
        except (ImportError, AttributeError):
            pass
        mode_type = os.environ.get("KUAVO_MODE_MSG_TYPE", DEFAULT_MODE_MSG_TYPE)
        mode_msg_cls = _resolve_msg_class(mode_type)
    except ImportError as exc:
        raise KuavoSimError(
            "ROS Python packages are unavailable. Run inside the sourced Kuavo "
            "container for runtime demos."
        ) from exc
    except AttributeError as exc:
        raise KuavoSimError(
            "ROS message type for mode feedback is unavailable. Set "
            "KUAVO_MODE_MSG_TYPE, for example std_msgs/Int8 or std_msgs/Int32."
        ) from exc
    return rospy, geometry_msg, sensor_msg, std_msg, kuavo_msg, kuavo_srv, mode_msg_cls


class KuavoSim:
    MODE_SERVICE = "/mobile_manipulator_mpc_control"

    def __init__(
        self,
        lb_api_dir=DEFAULT_LB_API_DIR,
        limits=None,
        prefer_lb_api=True,
        node_name="kuavo_sim_platform",
        auto_init_node=True,
    ):
        (
            self.rospy,
            geometry_msg,
            sensor_msg,
            std_msg,
            kuavo_msg,
            kuavo_srv,
            mode_msg_cls,
        ) = _require_ros()
        self._change_torso_mode_cls = kuavo_srv.changeTorsoCtrlMode
        self.log = _Log(self.rospy)
        self.limits = dict(DEFAULT_LIMITS)
        if limits:
            self.limits.update(limits)

        if auto_init_node and not self.rospy.core.is_initialized():
            self.rospy.init_node(node_name, anonymous=True, disable_signals=True)

        self.base = BaseControl(self.rospy, geometry_msg.Twist, self.log, self.limits)
        self.arm = ArmControl(
            self.rospy, sensor_msg.JointState, kuavo_msg, kuavo_srv, self.log
        )
        self.lower_body = LowerBodyControl(
            self.rospy, sensor_msg.JointState, geometry_msg.Twist, kuavo_srv, self.log
        )
        self.head_hand = HeadHandControl(self.rospy, kuavo_msg, self.log)
        self.state = StateMonitor(self.rospy, mode_msg_cls, std_msg.Float32, self.log)
        self._lb_api = (
            self._try_import_lb_api(lb_api_dir) if prefer_lb_api else None
        )

    def _try_import_lb_api(self, lb_api_dir):
        if lb_api_dir and os.path.isdir(lb_api_dir) and lb_api_dir not in sys.path:
            sys.path.insert(0, lb_api_dir)
        try:
            module = importlib.import_module("lb_ctrl_api")
        except ImportError as exc:
            self.log.warn("lb_ctrl_api import failed: %s", exc)
            return None
        if not hasattr(module, "set_control_mode"):
            self.log.warn("lb_ctrl_api has no set_control_mode(int)")
            return None
        self.log.info("using lb_ctrl_api.set_control_mode for mode switching")
        return module

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.fail_safe()
        return False

    def wait_ready(self, timeout=30.0):
        if not self.state.wait_ready(self.base, timeout=timeout):
            raise KuavoSimError("Kuavo runtime is not ready")
        return True

    def _set_mode_service(self, mode_int, timeout=5.0):
        try:
            self.rospy.wait_for_service(self.MODE_SERVICE, timeout=timeout)
            client = self.rospy.ServiceProxy(
                self.MODE_SERVICE, self._change_torso_mode_cls
            )
            response = client(control_mode=mode_int)
        except Exception as exc:
            raise KuavoSimError(
                f"{self.MODE_SERVICE} call failed for mode {mode_int}: {exc}"
            ) from exc
        if not getattr(response, "result", False):
            message = getattr(response, "message", "")
            raise KuavoSimError(f"mode switch failed for {mode_int}: {message}")
        response_mode = int(getattr(response, "mode", mode_int))
        if response_mode != mode_int:
            raise KuavoSimError(
                f"mode service confirmed {response_mode}, expected {mode_int}"
            )
        self.log.info("mode service confirmed %d", mode_int)
        return True

    def set_mode(self, mode, confirm=True, timeout=5.0):
        mode_int = resolve_mode(mode)
        if confirm:
            return self._set_mode_service(mode_int, timeout=timeout)
        if self._lb_api is not None:
            result = self._lb_api.set_control_mode(mode_int)
            if result is False:
                raise KuavoSimError(f"set_control_mode({mode_int}) returned False")
            return True
        return self._set_mode_service(mode_int, timeout=timeout)

    def set_mode_base_only(self, confirm=True, timeout=5.0):
        return self.set_mode(CtrlMode.BaseOnly, confirm=confirm, timeout=timeout)

    def set_mode_no_control(self, confirm=True, timeout=5.0):
        return self.set_mode(CtrlMode.NoControl, confirm=confirm, timeout=timeout)

    def set_mode_arm_only(self, confirm=True, timeout=5.0):
        return self.set_mode(CtrlMode.ArmOnly, confirm=confirm, timeout=timeout)

    def set_mode_base_arm(self, confirm=True, timeout=5.0):
        return self.set_mode(CtrlMode.BaseArm, confirm=confirm, timeout=timeout)

    def set_mode_arm_ee_only(self, confirm=True, timeout=5.0):
        return self.set_mode(CtrlMode.ArmEeOnly, confirm=confirm, timeout=timeout)

    def cmd_vel(self, x=0.0, y=0.0, yaw=0.0):
        self.base.cmd_vel(x=x, y=y, yaw=yaw)

    def cmd_vel_world(self, x=0.0, y=0.0, yaw=0.0):
        self.base.cmd_vel_world(x=x, y=y, yaw=yaw)

    def move_for(self, duration, x=0.0, y=0.0, yaw=0.0, rate=20):
        self.base.move_for(duration=duration, x=x, y=y, yaw=yaw, rate=rate)

    def move_world_for(self, duration, x=0.0, y=0.0, yaw=0.0, rate=20):
        self.base.move_world_for(duration=duration, x=x, y=y, yaw=yaw, rate=rate)

    def stop_base(self, world=False, hold=0.3):
        self.base.stop_base(world=world, hold=hold)

    def cmd_pose(self, x=0.0, y=0.0, yaw=0.0, z=0.0, roll=0.0, pitch=0.0):
        self.base.cmd_pose(x=x, y=y, z=z, roll=roll, pitch=pitch, yaw=yaw)

    def cmd_pose_world(self, x=0.0, y=0.0, yaw=0.0, z=0.0, roll=0.0, pitch=0.0):
        self.base.cmd_pose_world(x=x, y=y, z=z, roll=roll, pitch=pitch, yaw=yaw)

    def set_quick_mode(self, mode, timeout=5.0):
        return self.lower_body.set_quick_mode(mode, timeout=timeout)

    def set_arm_control_mode(self, mode, timeout=5.0):
        return self.arm.set_arm_control_mode(mode, timeout=timeout)

    def arm_joint(self, joints, names=None):
        self.arm.arm_joint(joints=joints, names=names)

    def two_arm_hand_pose(self, left, right, frame=2):
        self.arm.two_arm_hand_pose(left=left, right=right, frame=frame)

    def solve_ik(self, left, right, frame=2, timeout=5.0):
        return self.arm.solve_ik(left=left, right=right, frame=frame, timeout=timeout)

    def solve_fk(self, joints, timeout=5.0):
        return self.arm.solve_fk(joints=joints, timeout=timeout)

    def execute_arm_action(self, action_name, timeout=5.0):
        return self.arm.execute_arm_action(action_name=action_name, timeout=timeout)

    def leg_joint(self, joints):
        self.lower_body.leg_joint(joints=joints)

    def torso_pose(self, x=0.0, y=0.0, z=0.0, roll=0.0, pitch=0.0, yaw=0.0):
        self.lower_body.torso_pose(
            x=x, y=y, z=z, roll=roll, pitch=pitch, yaw=yaw
        )

    def head_body_pose(self, **kwargs):
        self.head_hand.head_body_pose(**kwargs)

    def hand_position(self, left=None, right=None):
        self.head_hand.hand_position(left=left, right=right)

    def claw_command(self, data):
        self.head_hand.claw_command(data)

    def wait_pose_reached(self, timeout=10.0, since=None):
        return self.state.wait_reach_time("pose", timeout=timeout, since=since)

    def wait_arm_joint_reached(self, side="left", timeout=10.0, since=None):
        return self.state.wait_reach_time(
            f"arm_joint_{side}", timeout=timeout, since=since
        )

    def wait_arm_ee_reached(self, side="left", timeout=10.0, since=None):
        return self.state.wait_reach_time(f"arm_ee_{side}", timeout=timeout, since=since)

    def wait_leg_joint_reached(self, timeout=10.0, since=None):
        return self.state.wait_reach_time("leg_joint", timeout=timeout, since=since)

    def wait_torso_reached(self, timeout=10.0, since=None):
        return self.state.wait_reach_time("torso_pose", timeout=timeout, since=since)

    def fail_safe(self):
        try:
            self.stop_base()
        except Exception as exc:
            self.log.error("fail-safe stop_base failed: %s", exc)
        try:
            self.set_mode_no_control(confirm=False)
        except Exception as exc:
            self.log.error("fail-safe NoControl failed: %s", exc)
