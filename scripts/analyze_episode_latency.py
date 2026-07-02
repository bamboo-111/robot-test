#!/usr/bin/env python3
"""Summarize v0.2 episode latency artifacts."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EPISODES_DIR = ROOT / "outputs" / "episodes"
REPORTS_DIR = ROOT / "outputs" / "perf_reports"

ROS_CHECK_KEYS = [
    "python_check.rostopic_available_ms",
    "python_check.rostopic_list_ms",
    "python_check.cmd_vel_ms",
    "python_check.mobile_manipulator_mpc_control_ms",
]

SUMMARY_FIELDS = [
    "run_id",
    "task_name",
    "entry_type",
    "status",
    "ok",
    "total_duration_ms",
    "main_command_ms",
    "executor_total_ms",
    "capabilities_collect_ms",
    "artifact_write_ms",
    "safe_stop_total_ms",
    "safe_stop_command_ms",
    "ros_check_ms",
    "rostopic_available_ms",
    "rostopic_list_ms",
    "cmd_vel_ms",
    "mobile_manipulator_mpc_control_ms",
    "external_timing_available",
    "episode_dir",
]


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def as_ms(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return None


def sum_present(values: list[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return round(sum(present), 3)


def select_episode_dirs(args: argparse.Namespace) -> list[Path]:
    if args.episodes:
        return [(Path(value) if Path(value).is_absolute() else ROOT / value).resolve() for value in args.episodes]

    if not EPISODES_DIR.exists():
        return []

    episode_dirs = [path for path in EPISODES_DIR.iterdir() if path.is_dir()]
    episode_dirs.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    if args.latest is not None:
        episode_dirs = episode_dirs[: args.latest]
    return episode_dirs


def summarize_episode(episode_dir: Path) -> dict[str, Any]:
    metrics = read_json(episode_dir / "metrics.json")
    result = read_json(episode_dir / "result.json")
    latency = read_json(episode_dir / "latency_breakdown.json")
    external = read_json(episode_dir / "external_timing.json")
    safe_stop = read_json(episode_dir / "safe_stop.json")
    durations = external.get("durations_ms") if isinstance(external.get("durations_ms"), dict) else {}

    rostopic_available_ms = as_ms(durations.get("python_check.rostopic_available_ms"))
    rostopic_list_ms = as_ms(durations.get("python_check.rostopic_list_ms"))
    cmd_vel_ms = as_ms(durations.get("python_check.cmd_vel_ms"))
    mpc_ms = as_ms(durations.get("python_check.mobile_manipulator_mpc_control_ms"))

    safe_stop_total_ms = as_ms(latency.get("safe_stop_total_ms"))
    if safe_stop_total_ms is None:
        safe_stop_total_ms = as_ms(safe_stop.get("duration_sec") * 1000) if safe_stop.get("duration_sec") is not None else None

    try:
        episode_dir_text = str(episode_dir.relative_to(ROOT))
    except ValueError:
        episode_dir_text = str(episode_dir)

    return {
        "run_id": metrics.get("run_id") or result.get("run_id") or episode_dir.name,
        "task_name": metrics.get("task_name") or latency.get("task_name") or "",
        "entry_type": metrics.get("entry_type") or latency.get("entry_type") or "",
        "status": result.get("status") or ("completed" if metrics.get("ok") else "failed" if metrics else ""),
        "ok": metrics.get("ok"),
        "total_duration_ms": as_ms(latency.get("total_duration_ms")),
        "main_command_ms": as_ms(latency.get("main_command_ms")),
        "executor_total_ms": as_ms(latency.get("executor_total_ms")),
        "capabilities_collect_ms": as_ms(latency.get("capabilities_collect_ms")),
        "artifact_write_ms": as_ms(latency.get("artifact_write_ms")),
        "safe_stop_total_ms": safe_stop_total_ms,
        "safe_stop_command_ms": as_ms(latency.get("safe_stop_command_ms")),
        "ros_check_ms": sum_present([rostopic_available_ms, rostopic_list_ms, cmd_vel_ms, mpc_ms]),
        "rostopic_available_ms": rostopic_available_ms,
        "rostopic_list_ms": rostopic_list_ms,
        "cmd_vel_ms": cmd_vel_ms,
        "mobile_manipulator_mpc_control_ms": mpc_ms,
        "external_timing_available": bool(external.get("available")),
        "episode_dir": episode_dir_text,
    }


def format_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: format_cell(row.get(field)) for field in SUMMARY_FIELDS})


def write_markdown(path: Path, rows: list[dict[str, Any]], source_count: int) -> None:
    lines = [
        "# v0.2 latency summary",
        "",
        f"- generated_at: {dt.datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"- episodes_requested: {source_count}",
        f"- rows: {len(rows)}",
        "",
        "| " + " | ".join(SUMMARY_FIELDS) + " |",
        "| " + " | ".join(["---"] * len(SUMMARY_FIELDS)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(format_cell(row.get(field)) for field in SUMMARY_FIELDS) + " |")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def print_table(rows: list[dict[str, Any]]) -> None:
    compact_fields = [
        "run_id",
        "task_name",
        "entry_type",
        "ok",
        "total_duration_ms",
        "main_command_ms",
        "capabilities_collect_ms",
        "safe_stop_command_ms",
        "ros_check_ms",
    ]
    print(",".join(compact_fields))
    for row in rows:
        print(",".join(format_cell(row.get(field)) for field in compact_fields))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Summarize episode latency artifacts")
    parser.add_argument("--latest", type=int, default=10, help="Analyze the latest N episode directories")
    parser.add_argument("--episodes", nargs="*", help="Explicit episode directories to analyze")
    parser.add_argument("--no-write", action="store_true", help="Print only; do not write report files")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.latest is not None and args.latest <= 0:
        print("[ERROR] --latest must be positive", file=sys.stderr)
        return 2

    episode_dirs = select_episode_dirs(args)
    rows = [summarize_episode(path) for path in episode_dirs]
    print_table(rows)

    if not args.no_write:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = REPORTS_DIR / f"{timestamp}_latency_summary.csv"
        md_path = REPORTS_DIR / f"{timestamp}_latency_summary.md"
        write_csv(csv_path, rows)
        write_markdown(md_path, rows, len(episode_dirs))
        print(f"[INFO] wrote {csv_path.relative_to(ROOT)}")
        print(f"[INFO] wrote {md_path.relative_to(ROOT)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
