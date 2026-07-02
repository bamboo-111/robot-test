"""File-based v0.2-alpha episode runner."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from .artifacts import (
    append_event,
    now_iso,
    write_final_artifacts,
    write_initial_artifacts,
    write_safe_stop_artifacts,
    write_status,
)
from .executors import SafeStopResult, run_executor, run_safe_stop, skipped_safe_stop
from .index import append_run_index
from .policy import PolicyError, check_policy, load_policy
from .schema import ConfigError, dump_yaml, load_yaml, resolve_config, sanitize_task_name


@dataclass(frozen=True)
class EpisodeResult:
    run_id: str
    episode_dir: Path
    status: str
    ok: bool
    duration_sec: float
    result: dict


def make_run_id(task_name: str) -> str:
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    return f"{timestamp}_{sanitize_task_name(task_name)}_{uuid.uuid4().hex[:4]}"


def repo_root_from_here() -> Path:
    return Path(__file__).resolve().parents[2]


def make_placeholder_config(
    raw_config: dict,
    operator_override: str | None,
    repo_root: Path,
    task_name: str,
) -> dict:
    return {
        "schema_version": str(raw_config.get("schema_version", "0.2")),
        "repo_root": str(repo_root),
        "task_name": sanitize_task_name(task_name),
        "entry_type": str(raw_config.get("entry_type", "unknown")),
        "operator": str(operator_override or raw_config.get("operator") or "unknown"),
        "permission_level": str(raw_config.get("permission_level", "read_only")),
        "timeout_sec": int(raw_config.get("timeout_sec", 30) or 30),
        "artifacts": {},
        "safety": {},
        "check": raw_config.get("check") or {},
        "scenario": raw_config.get("scenario") or {},
        "success_criteria": raw_config.get("success_criteria") or {},
    }


def safe_stop_to_dict(result: SafeStopResult) -> dict:
    return {
        "attempted": result.attempted,
        "ok": result.ok,
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "command": result.command,
        "duration_sec": result.duration_sec,
        "failure_reason": result.failure_reason,
        "reason": result.reason,
    }


def scenario_requires_safe_stop(config: dict) -> bool:
    safety = config.get("safety") or {}
    return (
        config.get("entry_type") == "scenario"
        and bool(safety.get("allow_motion"))
        and bool(safety.get("safe_stop_on_exit"))
    )


def run_episode(config_path: Path, operator_override: str | None = None, repo_root: Path | None = None) -> EpisodeResult:
    repo_root = (repo_root or repo_root_from_here()).resolve()
    config_path = config_path if config_path.is_absolute() else repo_root / config_path
    policy_path = repo_root / "configs" / "policies" / "v0.2_policy.yaml"

    raw_config_text = config_path.read_text(encoding="utf-8")
    task_name = config_path.stem
    run_id = make_run_id(task_name)
    outputs_dir = repo_root / "outputs"
    episode_dir = outputs_dir / "episodes" / run_id
    episode_dir.mkdir(parents=True, exist_ok=False)

    started_at = now_iso()
    start_monotonic = time.monotonic()
    status = "failed"
    ok = False
    exit_code = 1
    command = ""
    stdout = ""
    stderr = ""
    failure_reason: str | None = None
    safe_stop: dict | None = None
    raw_config: dict = {"task_name": task_name}
    resolved_config = make_placeholder_config(raw_config, operator_override, repo_root, task_name)

    write_initial_artifacts(episode_dir, run_id, raw_config_text, resolved_config)

    try:
        raw_config = load_yaml(config_path)
        task_name = str(raw_config.get("task_name") or config_path.stem)
        resolved_config = resolve_config(raw_config, repo_root, operator_override=operator_override)
        dump_yaml(episode_dir / "resolved_config.yaml", resolved_config)

        write_status(episode_dir, run_id, "preflight", "policy")
        append_event(episode_dir, "preflight", "checking policy")
        policy = load_policy(policy_path)
        check_policy(resolved_config, policy)

        append_event(episode_dir, "preflight", "preflight completed")
        write_status(episode_dir, run_id, "running", "executor")
        append_event(episode_dir, "running", "executor started", entry_type=resolved_config["entry_type"])

        if resolved_config["entry_type"] == "scenario":
            scenario = resolved_config.get("scenario") or {}
            scenario_source = Path(str(scenario.get("abs_file", "")))
            scenario_copy = episode_dir / "scenario.yaml"
            scenario_copy.write_text(scenario_source.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
            append_event(
                episode_dir,
                "scenario_start",
                "running scenario",
                scenario=scenario.get("file"),
                container_file=scenario.get("container_file"),
            )

        try:
            try:
                executor_result = run_executor(resolved_config, repo_root)
            except Exception as exc:
                if resolved_config["entry_type"] == "scenario":
                    append_event(
                        episode_dir,
                        "scenario_end",
                        "scenario raised exception",
                        ok=False,
                        error=str(exc),
                    )
                raise
            if resolved_config["entry_type"] == "scenario":
                append_event(
                    episode_dir,
                    "scenario_end",
                    "scenario completed",
                    exit_code=executor_result.exit_code,
                    ok=executor_result.ok,
                )
        finally:
            if scenario_requires_safe_stop(resolved_config):
                append_event(episode_dir, "safe_stop_start", "running restore script")
                try:
                    safe_stop_result = run_safe_stop(repo_root)
                except Exception as exc:
                    safe_stop_result = SafeStopResult(
                        attempted=True,
                        ok=False,
                        exit_code=2,
                        stdout="",
                        stderr=str(exc),
                        command="",
                        duration_sec=None,
                        failure_reason=str(exc),
                    )
                safe_stop = safe_stop_to_dict(safe_stop_result)
                write_safe_stop_artifacts(episode_dir, safe_stop)
                append_event(
                    episode_dir,
                    "safe_stop_end",
                    "restore finished",
                    exit_code=safe_stop_result.exit_code,
                    ok=safe_stop_result.ok,
                )
            elif resolved_config["entry_type"] == "scenario":
                safe_stop_result = skipped_safe_stop("allow_motion=false")
                safe_stop = safe_stop_to_dict(safe_stop_result)
                write_safe_stop_artifacts(episode_dir, safe_stop)

        exit_code = executor_result.exit_code
        ok = executor_result.ok
        command = executor_result.command
        stdout = executor_result.stdout
        stderr = executor_result.stderr
        status = "completed" if ok else "failed"
        if not ok:
            failure_reason = stderr.strip() or stdout.strip() or f"exit_code={exit_code}"
        append_event(episode_dir, status, "executor completed", exit_code=exit_code)
    except (ConfigError, PolicyError, ValueError) as exc:
        status = "failed"
        ok = False
        exit_code = 1
        stderr = str(exc)
        failure_reason = str(exc)
        append_event(episode_dir, "failed", "runner validation failed", error=str(exc))
    except Exception as exc:
        status = "failed"
        ok = False
        exit_code = 2
        stderr = str(exc)
        failure_reason = str(exc)
        append_event(episode_dir, "failed", "runner failed", error=str(exc))

    finished_at = now_iso()
    duration_sec = round(time.monotonic() - start_monotonic, 3)

    result = write_final_artifacts(
        episode_dir=episode_dir,
        repo_root=repo_root,
        run_id=run_id,
        config=resolved_config,
        status=status,
        ok=ok,
        exit_code=exit_code,
        command=command,
        stdout=stdout,
        stderr=stderr,
        started_at=started_at,
        finished_at=finished_at,
        duration_sec=duration_sec,
        failure_reason=failure_reason,
        safe_stop=safe_stop,
    )

    try:
        index_entry = {
            "schema_version": resolved_config["schema_version"],
            "run_id": run_id,
            "task_name": resolved_config["task_name"],
            "entry_type": resolved_config["entry_type"],
            "operator": resolved_config["operator"],
            "status": status,
            "ok": ok,
            "duration_sec": duration_sec,
            "episode_dir": str(episode_dir.relative_to(repo_root)),
            "created_at": started_at,
        }
        if resolved_config["entry_type"] == "scenario":
            index_entry["scenario"] = (resolved_config.get("scenario") or {}).get("file")
        if safe_stop is not None:
            index_entry["safe_stop_attempted"] = bool(safe_stop.get("attempted"))
            index_entry["safe_stop_ok"] = safe_stop.get("ok")
        append_run_index(
            outputs_dir,
            index_entry,
        )
    except OSError as exc:
        append_event(episode_dir, "failed", "run_index append failed", error=str(exc))

    return EpisodeResult(
        run_id=run_id,
        episode_dir=episode_dir,
        status=status,
        ok=ok,
        duration_sec=duration_sec,
        result=result,
    )
