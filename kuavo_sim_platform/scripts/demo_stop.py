#!/usr/bin/env python3
"""Best-effort emergency base stop for Kuavo 5-W."""

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from kuavo_sim import KuavoSim


def main():
    with KuavoSim() as bot:
        bot.stop_base(hold=1.0)
        bot.set_mode_no_control(confirm=False)


if __name__ == "__main__":
    main()
