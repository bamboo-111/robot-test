#!/usr/bin/env python3
"""Compatibility wrapper for the canonical Web-console safe probe."""

from pathlib import Path
import runpy

CANONICAL = Path(__file__).resolve().parents[2] / "kuavo_sim_platform" / "imported_scripts" / "bc_safe_probe.py"

if __name__ == "__main__":
    runpy.run_path(str(CANONICAL), run_name="__main__")
