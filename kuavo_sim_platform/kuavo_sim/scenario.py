"""YAML scenario runner for KuavoSim."""

import argparse
import sys

from .modes import resolve_mode


SUPPORTED_ACTIONS = {
    "wait_ready",
    "set_mode",
    "set_quick_mode",
    "set_arm_control_mode",
    "cmd_vel",
    "cmd_vel_world",
    "move_for",
    "move_world_for",
    "cmd_pose",
    "cmd_pose_world",
    "stop_base",
    "arm_joint",
    "two_arm_hand_pose",
    "leg_joint",
    "torso_pose",
    "head_body_pose",
    "hand_position",
    "sleep",
}


def load_scenario(path):
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("PyYAML is required to load scenario files") from exc
    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    return validate_scenario(data)


def validate_scenario(data):
    if not isinstance(data, dict):
        raise ValueError("scenario must be a mapping")
    if "steps" not in data:
        raise ValueError("scenario missing required key: steps")
    if not isinstance(data["steps"], list):
        raise ValueError("scenario steps must be a list")
    for index, step in enumerate(data["steps"], start=1):
        if not isinstance(step, dict):
            raise ValueError(f"step {index} must be a mapping")
        action = step.get("action")
        if action not in SUPPORTED_ACTIONS:
            valid = ", ".join(sorted(SUPPORTED_ACTIONS))
            raise ValueError(f"step {index} unknown action {action!r}; valid: {valid}")
        if action == "set_mode":
            if "mode" not in step:
                raise ValueError(f"step {index} set_mode missing mode")
            resolve_mode(step["mode"])
        if action in {"move_for", "move_world_for"} and "duration" not in step:
            raise ValueError(f"step {index} {action} missing duration")
        if action == "arm_joint" and "joints" not in step:
            raise ValueError(f"step {index} arm_joint missing joints")
        if action == "leg_joint" and "joints" not in step:
            raise ValueError(f"step {index} leg_joint missing joints")
        if action == "two_arm_hand_pose" and (
            "left" not in step or "right" not in step
        ):
            raise ValueError(f"step {index} two_arm_hand_pose missing left/right")
    return data


def run_scenario(bot, scenario):
    for step in scenario["steps"]:
        action = step["action"]
        if action == "wait_ready":
            bot.wait_ready(timeout=step.get("timeout", 30.0))
        elif action == "set_mode":
            bot.set_mode(step["mode"], timeout=step.get("timeout", 5.0))
        elif action == "set_quick_mode":
            bot.set_quick_mode(step.get("mode", 0), timeout=step.get("timeout", 5.0))
        elif action == "set_arm_control_mode":
            bot.set_arm_control_mode(
                step.get("mode", 2), timeout=step.get("timeout", 5.0)
            )
        elif action == "cmd_vel":
            bot.cmd_vel(x=step.get("x", 0.0), y=step.get("y", 0.0), yaw=step.get("yaw", 0.0))
        elif action == "cmd_vel_world":
            bot.cmd_vel_world(
                x=step.get("x", 0.0), y=step.get("y", 0.0), yaw=step.get("yaw", 0.0)
            )
        elif action == "move_for":
            bot.move_for(
                duration=step["duration"],
                x=step.get("x", 0.0),
                y=step.get("y", 0.0),
                yaw=step.get("yaw", 0.0),
                rate=step.get("rate", 20),
            )
        elif action == "move_world_for":
            bot.move_world_for(
                duration=step["duration"],
                x=step.get("x", 0.0),
                y=step.get("y", 0.0),
                yaw=step.get("yaw", 0.0),
                rate=step.get("rate", 20),
            )
        elif action == "cmd_pose":
            since = _now()
            bot.cmd_pose(
                x=step.get("x", 0.0),
                y=step.get("y", 0.0),
                z=step.get("z", 0.0),
                roll=step.get("roll", 0.0),
                pitch=step.get("pitch", 0.0),
                yaw=step.get("yaw", 0.0),
            )
            if step.get("wait", True):
                _sleep_reach(bot.wait_pose_reached(timeout=step.get("timeout", 10.0), since=since), bot)
        elif action == "cmd_pose_world":
            since = _now()
            bot.cmd_pose_world(
                x=step.get("x", 0.0),
                y=step.get("y", 0.0),
                z=step.get("z", 0.0),
                roll=step.get("roll", 0.0),
                pitch=step.get("pitch", 0.0),
                yaw=step.get("yaw", 0.0),
            )
            if step.get("wait", True):
                _sleep_reach(bot.wait_pose_reached(timeout=step.get("timeout", 10.0), since=since), bot)
        elif action == "stop_base":
            bot.stop_base(hold=step.get("hold", 0.3))
        elif action == "arm_joint":
            since = _now()
            bot.arm_joint(step["joints"])
            if step.get("wait", True):
                _sleep_reach(bot.wait_arm_joint_reached(timeout=step.get("timeout", 10.0), since=since), bot)
        elif action == "two_arm_hand_pose":
            since = _now()
            bot.two_arm_hand_pose(step["left"], step["right"], frame=step.get("frame", 2))
            if step.get("wait", True):
                _sleep_reach(bot.wait_arm_ee_reached(timeout=step.get("timeout", 10.0), since=since), bot)
        elif action == "leg_joint":
            since = _now()
            bot.leg_joint(step["joints"])
            if step.get("wait", True):
                _sleep_reach(bot.wait_leg_joint_reached(timeout=step.get("timeout", 10.0), since=since), bot)
        elif action == "torso_pose":
            since = _now()
            bot.torso_pose(
                x=step.get("x", 0.0),
                y=step.get("y", 0.0),
                z=step.get("z", 0.0),
                roll=step.get("roll", 0.0),
                pitch=step.get("pitch", 0.0),
                yaw=step.get("yaw", 0.0),
            )
            if step.get("wait", True):
                _sleep_reach(bot.wait_torso_reached(timeout=step.get("timeout", 10.0), since=since), bot)
        elif action == "head_body_pose":
            bot.head_body_pose(**{key: value for key, value in step.items() if key != "action"})
        elif action == "hand_position":
            bot.hand_position(left=step.get("left"), right=step.get("right"))
        elif action == "sleep":
            import time

            time.sleep(float(step.get("duration", 1.0)))
        else:
            raise ValueError(f"unsupported action after validation: {action}")


def _now():
    import time

    return time.time()


def _sleep_reach(reach_time, bot):
    if reach_time is not None:
        bot.rospy.sleep(float(reach_time) + 0.2)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run a KuavoSim YAML scenario")
    parser.add_argument("scenario", help="path to scenario YAML")
    args = parser.parse_args(argv)
    scenario = load_scenario(args.scenario)
    from .client import KuavoSim

    with KuavoSim() as bot:
        run_scenario(bot, scenario)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"scenario failed: {exc}", file=sys.stderr)
        raise
