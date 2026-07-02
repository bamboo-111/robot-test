#!/usr/bin/env python3
"""Benchmark runner for whitelisted episode experiments (B-4).

Runs a benchmark config that lists one or more experiment YAMLs and a
``runs_per_experiment`` count, executes each episode through the standard
episode runner, and writes an aggregate summary (csv/json/md) under
``outputs/benchmarks/<benchmark_id>/``.

Safety rules (enforced here, not just by convention):
  * Only check experiments are allowed by default.
  * Any benchmark whose config references ``base_probe`` or a scenario /
    motion entry is refused unless ``--allow-motion`` is passed (operator A
    approval gate). B/C must not pass that flag.
  * The runner only ever invokes ``run_episode``; it never shells out to
    PowerShell, Docker, restore, /cmd_vel, or arbitrary scripts.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kuavo_sim_platform.episode import run_episode  # noqa: E402

BENCHMARKS_DIR = ROOT / "configs" / "benchmarks"
OUTPUT_DIR = ROOT / "outputs" / "benchmarks"

# Experiments that involve motion and therefore require --allow-motion.
MOTION_TASK_KEYWORDS = ("base_probe", "base_forward", "move_for", "scenario")


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 3)
    k = (len(ordered) - 1) * pct
    lo = int(k)
    hi = min(lo + 1, len(ordered) - 1)
    fraction = k - lo
    return round(ordered[lo] + (ordered[hi] - ordered[lo]) * fraction, 3)


def safe_mean(values: list[float]) -> float | None:
    return round(statistics.mean(values), 3) if values else None


def experiment_involves_motion(experiment_path: Path) -> bool:
    """Heuristic gate: treat scenario entry types and known motion tasks as motion."""
    try:
        with experiment_path.open("r", encoding="utf-8") as handle:
            cfg = yaml.safe_load(handle) or {}
    except (OSError, yaml.YAMLError):
        return True  # be conservative: if we can't read it, treat as motion
    entry_type = str(cfg.get("entry_type", "")).strip()
    task_name = str(cfg.get("task_name", "")).strip().lower()
    if entry_type == "scenario":
        return True
    return any(keyword in task_name for keyword in MOTION_TASK_KEYWORDS)


def load_benchmark_config(config_path: Path, allow_motion: bool) -> dict[str, Any]:
    with config_path.open("r", encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle) or {}
    if not isinstance(cfg, dict):
        raise ValueError(f"benchmark config must be a mapping: {config_path}")

    benchmark_id = str(cfg.get("benchmark_id") or config_path.stem)
    experiment_configs = cfg.get("experiment_configs") or []
    if not experiment_configs or not isinstance(experiment_configs, list):
        raise ValueError("benchmark config must list experiment_configs")

    resolved_experiments: list[Path] = []
    for entry in experiment_configs:
        exp_path = (ROOT / str(entry)).resolve() if not Path(str(entry)).is_absolute() else Path(str(entry))
        if not exp_path.is_file():
            raise FileNotFoundError(f"experiment config not found: {exp_path}")
        if experiment_involves_motion(exp_path) and not allow_motion:
            raise PermissionError(
                f"experiment {exp_path.name} involves motion/base_probe; "
                "pass --allow-motion (operator A only) to run this benchmark"
            )
        resolved_experiments.append(exp_path)

    runs_per_experiment = int(cfg.get("runs_per_experiment", 1))
    if runs_per_experiment <= 0:
        raise ValueError("runs_per_experiment must be positive")
    operator = str(cfg.get("operator") or "B")
    return {
        "benchmark_id": benchmark_id,
        "description": str(cfg.get("description") or ""),
        "experiments": resolved_experiments,
        "runs_per_experiment": runs_per_experiment,
        "operator": operator,
    }


def summarize_benchmark(run_ids: list[str]) -> dict[str, Any]:
    """Compute aggregate metrics across the given run_ids."""
    episodes_dir = ROOT / "outputs" / "episodes"
    durations: list[float] = []
    main_command: list[float] = []
    capabilities_collect: list[float] = []
    ros_check: list[float] = []
    external_timing_rates: list[bool] = []
    ok_flags: list[bool] = []

    ros_check_keys = [
        "python_check.rostopic_available_ms",
        "python_check.rostopic_list_ms",
        "python_check.cmd_vel_ms",
        "python_check.mobile_manipulator_mpc_control_ms",
    ]

    for run_id in run_ids:
        episode_dir = episodes_dir / run_id
        latency = read_json(episode_dir / "latency_breakdown.json")
        external = read_json(episode_dir / "external_timing.json")
        durations_ms = external.get("durations_ms") if isinstance(external.get("durations_ms"), dict) else {}

        if latency.get("total_duration_ms") is not None:
            durations.append(float(latency["total_duration_ms"]))
        if latency.get("main_command_ms") is not None:
            main_command.append(float(latency["main_command_ms"]))
        if latency.get("capabilities_collect_ms") is not None:
            capabilities_collect.append(float(latency["capabilities_collect_ms"]))
        ros_parts = [durations_ms.get(k) for k in ros_check_keys]
        ros_parts = [float(v) for v in ros_parts if v is not None]
        if ros_parts:
            ros_check.append(round(sum(ros_parts), 3))
        external_timing_rates.append(bool(external.get("available")))
        # ok flag comes from metrics/result, default False if unreadable
        metrics = read_json(episode_dir / "metrics.json")
        ok_flags.append(bool(metrics.get("ok")))

    total_runs = len(run_ids)
    success_count = sum(1 for ok in ok_flags if ok)
    return {
        "total_runs": total_runs,
        "success_rate": round(success_count / total_runs, 4) if total_runs else 0.0,
        "failure_rate": round((total_runs - success_count) / total_runs, 4) if total_runs else 0.0,
        "mean_duration_ms": safe_mean(durations),
        "p50_duration_ms": percentile(durations, 0.50),
        "p90_duration_ms": percentile(durations, 0.90),
        "mean_main_command_ms": safe_mean(main_command),
        "mean_capabilities_collect_ms": safe_mean(capabilities_collect),
        "mean_ros_check_ms": safe_mean(ros_check),
        "external_timing_available_rate": round(sum(1 for r in external_timing_rates if r) / total_runs, 4)
        if total_runs
        else 0.0,
    }


def write_summary(benchmark_dir: Path, benchmark_id: str, summary: dict[str, Any], run_ids: list[str], benchmark_config: dict[str, Any]) -> None:
    benchmark_dir.mkdir(parents=True, exist_ok=True)

    # Persist the resolved benchmark config for reproducibility.
    with (benchmark_dir / "benchmark_config.yaml").open("w", encoding="utf-8", newline="\n") as handle:
        yaml.safe_dump(
            {
                "benchmark_id": benchmark_id,
                "description": benchmark_config["description"],
                "experiments": [str(p.relative_to(ROOT)) for p in benchmark_config["experiments"]],
                "runs_per_experiment": benchmark_config["runs_per_experiment"],
                "operator": benchmark_config["operator"],
            },
            handle,
            sort_keys=False,
            allow_unicode=True,
        )

    (benchmark_dir / "run_ids.txt").write_text("\n".join(run_ids) + "\n", encoding="utf-8")

    summary_fields = [
        "total_runs",
        "success_rate",
        "failure_rate",
        "mean_duration_ms",
        "p50_duration_ms",
        "p90_duration_ms",
        "mean_main_command_ms",
        "mean_capabilities_collect_ms",
        "mean_ros_check_ms",
        "external_timing_available_rate",
    ]
    (benchmark_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    import csv

    with (benchmark_dir / "summary.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=summary_fields)
        writer.writeheader()
        writer.writerow({field: summary.get(field) for field in summary_fields})

    md_lines = [
        f"# Benchmark: {benchmark_id}",
        "",
        f"- generated_at: {dt.datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"- total_runs: {summary['total_runs']}",
        f"- operator: {benchmark_config['operator']}",
        "",
        "| metric | value |",
        "| --- | --- |",
    ]
    for field in summary_fields:
        md_lines.append(f"| {field} | {summary.get(field)} |")
    md_lines.append("")
    (benchmark_dir / "summary.md").write_text("\n".join(md_lines), encoding="utf-8", newline="\n")


def run_benchmark(config_path: Path, operator_override: str | None, allow_motion: bool, dry_run: bool) -> int:
    benchmark = load_benchmark_config(config_path, allow_motion)
    benchmark_id = benchmark["benchmark_id"]
    operator = operator_override or benchmark["operator"]
    runs_per = benchmark["runs_per_experiment"]

    print(f"[INFO] benchmark={benchmark_id} operator={operator} runs_per_experiment={runs_per}")
    print(f"[INFO] experiments: {[p.name for p in benchmark['experiments']]}")

    if dry_run:
        print("[INFO] dry-run: no episodes will be executed")
        return 0

    run_ids: list[str] = []
    total_planned = runs_per * len(benchmark["experiments"])
    executed = 0
    for exp_path in benchmark["experiments"]:
        for i in range(runs_per):
            executed += 1
            print(f"[INFO] run {executed}/{total_planned}: {exp_path.name}")
            try:
                result = run_episode(exp_path, operator_override=operator, repo_root=ROOT)
                run_ids.append(result.run_id)
                print(f"[INFO]   run_id={result.run_id} ok={result.ok} status={result.status} duration={result.duration_sec}s")
            except Exception as exc:  # noqa: BLE001 - a single episode must not abort the benchmark
                print(f"[WARN]   episode raised and was skipped: {exc}")

    if not run_ids:
        print("[ERROR] no episodes completed; nothing to summarize")
        return 1

    summary = summarize_benchmark(run_ids)
    benchmark_dir = OUTPUT_DIR / benchmark_id
    write_summary(benchmark_dir, benchmark_id, summary, run_ids, benchmark)

    print(f"[INFO] summary written to {benchmark_dir.relative_to(ROOT)}")
    print(f"[INFO] total_runs={summary['total_runs']} success_rate={summary['success_rate']} "
          f"mean_duration_ms={summary['mean_duration_ms']} p50={summary['p50_duration_ms']} "
          f"p90={summary['p90_duration_ms']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a whitelisted episode benchmark")
    parser.add_argument("--config", required=True, help="Path to a benchmark YAML under configs/benchmarks/")
    parser.add_argument("--operator", help="Override the operator recorded on each episode")
    parser.add_argument("--allow-motion", action="store_true", help="Permit motion/base_probe benchmarks (operator A only)")
    parser.add_argument("--dry-run", action="store_true", help="Validate the benchmark config without running episodes")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config_path = (ROOT / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config).resolve()
    if not config_path.is_file():
        print(f"[ERROR] benchmark config not found: {config_path}", file=sys.stderr)
        return 2
    try:
        return run_benchmark(config_path, args.operator, args.allow_motion, args.dry_run)
    except (PermissionError, FileNotFoundError, ValueError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
