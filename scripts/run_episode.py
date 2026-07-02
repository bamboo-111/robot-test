#!/usr/bin/env python3
"""Run a v0.2 file-based episode."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kuavo_sim_platform.episode import run_episode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a Kuavo v0.2 episode")
    parser.add_argument("--config", required=True, help="Path to experiment config YAML")
    parser.add_argument("--operator", help="Override operator from the config")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run_episode(Path(args.config), operator_override=args.operator, repo_root=ROOT)
    except Exception as exc:
        print(f"[ERROR] runner failed before artifacts were complete: {exc}", file=sys.stderr)
        return 2

    rel_episode = result.episode_dir.relative_to(ROOT)
    print(f"[INFO] episode created: {rel_episode}")
    print(f"[INFO] status: {result.status}")
    print(f"[INFO] ok: {str(result.ok).lower()}")
    print(f"[INFO] duration_sec: {result.duration_sec}")
    print(f"[INFO] metrics: {rel_episode / 'metrics.json'}")

    if result.ok:
        return 0
    print(f"[ERROR] episode failed: {rel_episode}", file=sys.stderr)
    failure_reason = result.result.get("tail_stderr") or result.result.get("tail_stdout") or "see result.json"
    print(f"[ERROR] failure_reason: {failure_reason}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
