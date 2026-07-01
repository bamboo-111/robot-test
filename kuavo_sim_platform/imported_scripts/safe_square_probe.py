#!/usr/bin/env python3
"""Visible safe rectangle probe for the Kuavo web imported-script runner."""

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from kuavo_sim import KuavoSim


STEP_DURATION = 1.0
STEP_SPEED = 0.05
TURN_DURATION = 1.0
TURN_YAW = 0.05
EDGE_STEPS = 4


def stop_and_pause(bot):
    bot.stop_base()


def drive_body_square(bot):
    for _ in range(4):
        for _ in range(EDGE_STEPS):
            bot.move_for(duration=STEP_DURATION, x=STEP_SPEED, y=0.0, yaw=0.0)
            stop_and_pause(bot)
        bot.move_for(duration=TURN_DURATION, x=0.0, y=0.0, yaw=TURN_YAW)
        stop_and_pause(bot)


def drift_world_frame(bot):
    legs = (
        (STEP_SPEED, 0.0),
        (0.0, STEP_SPEED),
        (-STEP_SPEED, 0.0),
        (0.0, -STEP_SPEED),
    )
    for x, y in legs:
        for _ in range(EDGE_STEPS):
            bot.move_world_for(duration=STEP_DURATION, x=x, y=y, yaw=0.0)
            stop_and_pause(bot)


def main():
    with KuavoSim() as bot:
        bot.wait_ready(timeout=30.0)
        bot.set_mode_base_only()
        try:
            drive_body_square(bot)
            drift_world_frame(bot)
        finally:
            bot.stop_base()
            bot.set_mode_no_control()


if __name__ == "__main__":
    main()
