#!/usr/bin/env python3
"""Forward base demo for Kuavo 5-W after probe succeeds."""

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from kuavo_sim import KuavoSim


def main():
    with KuavoSim() as bot:
        bot.wait_ready(timeout=30.0)
        bot.set_mode_base_only()
        bot.move_for(duration=2.0, x=0.20, y=0.0, yaw=0.0)
        bot.stop_base()
        bot.set_mode_no_control()


if __name__ == "__main__":
    main()
