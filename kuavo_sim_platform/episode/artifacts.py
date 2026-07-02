"""Artifact writing for file-based episodes."""

from __future__ import annotations

import json
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from .schema import SCHEMA_VERSION, dump_yaml


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def write_json(path: Path, data: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def write_text(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text or "")


def append_event(episode_dir: Path, stage: str, message: str, **fields: Any) -> None:
    event = {
        "schema_version": SCHEMA_VERSION,
        "t": now_iso(),
        "stage": stage,
        "message": message,
    }
    event.update(fields)
    with (episode_dir / "events.jsonl").open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True))
        handle.write("\n")


def write_status(episode_dir: Path, run_id: str, status: str, current_stage: str) -> None:
    write_json(
        episode_dir / "status.json",
        {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "status": status,
            "current_stage": current_stage,
            "updated_at": now_iso(),
        },
    )


def command_output(args: list[str], cwd: Path) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            args,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )
        return completed.returncode, (completed.stdout or completed.stderr or "").strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)


def collect_git_info(repo_root: Path) -> dict[str, Any]:
    commit_code, commit = command_output(["git", "rev-parse", "--short", "HEAD"], repo_root)
    branch_code, branch = command_output(["git", "branch", "--show-current"], repo_root)
    dirty_code, dirty_output = command_output(["git", "status", "--short"], repo_root)
    return {
        "commit": commit if commit_code == 0 else None,
        "branch": branch if branch_code == 0 else None,
        "dirty": bool(dirty_output) if dirty_code == 0 else None,
    }


def collect_capabilities(repo_root: Path) -> dict[str, Any]:
    docker_code, docker_version = command_output(["docker", "--version"], repo_root)
    container_code, container_state = command_output(
        ["docker", "inspect", "-f", "{{.State.Running}}", "kuavo5w_sim"],
        repo_root,
    )
    web_code = 1
    web_note = "not checked"
    try:
        import http.client

        conn = http.client.HTTPConnection("127.0.0.1", 8765, timeout=2)
        conn.request("GET", "/")
        response = conn.getresponse()
        response.read(128)
        conn.close()
        web_code = 0 if 200 <= response.status < 500 else 1
        web_note = f"HTTP {response.status}"
    except OSError as exc:
        web_note = str(exc)

    return {
        "schema_version": SCHEMA_VERSION,
        "container_name": "kuavo5w_sim",
        "container_running": container_state.strip().lower() == "true" if container_code == 0 else False,
        "docker_cli_available": docker_code == 0,
        "docker_version": docker_version if docker_code == 0 else None,
        "web_backend_available": web_code == 0,
        "web_backend_note": web_note,
        "platform": platform.platform(),
        "python_version": sys.version.split()[0],
        "git": collect_git_info(repo_root),
        "can_run_check": True,
        "can_run_scenario": None,
        "can_run_script": None,
        "notes": [],
    }


def write_initial_artifacts(
    episode_dir: Path,
    run_id: str,
    raw_config_text: str,
    resolved_config: dict[str, Any],
) -> None:
    write_status(episode_dir, run_id, "created", "created")
    append_event(episode_dir, "created", "episode created")
    write_text(episode_dir / "config.yaml", raw_config_text)
    dump_yaml(episode_dir / "resolved_config.yaml", resolved_config)
    write_text(episode_dir / "stdout.log", "")
    write_text(episode_dir / "stderr.log", "")
    write_text(episode_dir / "command.txt", "")


def write_final_artifacts(
    episode_dir: Path,
    repo_root: Path,
    run_id: str,
    config: dict[str, Any],
    status: str,
    ok: bool,
    exit_code: int,
    command: str,
    stdout: str,
    stderr: str,
    started_at: str,
    finished_at: str,
    duration_sec: float,
    failure_reason: str | None,
) -> dict[str, Any]:
    write_text(episode_dir / "stdout.log", stdout)
    write_text(episode_dir / "stderr.log", stderr)
    write_text(episode_dir / "command.txt", command)

    capabilities = collect_capabilities(repo_root)
    write_json(episode_dir / "capabilities.json", capabilities)

    metrics = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "task_name": config["task_name"],
        "entry_type": config["entry_type"],
        "operator": config["operator"],
        "permission_level": config["permission_level"],
        "start_time": started_at,
        "end_time": finished_at,
        "duration_sec": duration_sec,
        "timeout_sec": config["timeout_sec"],
        "exit_code": exit_code,
        "ok": ok,
        "success": ok,
        "failure_reason": failure_reason,
        "safe_stop_attempted": False,
        "safe_stop_ok": None,
        "stdout_log": "stdout.log",
        "stderr_log": "stderr.log",
        "config_path": "config.yaml",
        "resolved_config_path": "resolved_config.yaml",
    }
    write_json(episode_dir / "metrics.json", metrics)

    result = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "status": status,
        "ok": ok,
        "summary": f"{config['task_name']} {status}",
        "episode_dir": str(episode_dir.relative_to(repo_root)),
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_sec": duration_sec,
        "tail_stdout": tail_text(stdout),
        "tail_stderr": tail_text(stderr),
    }
    write_json(episode_dir / "result.json", result)

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "task_name": config["task_name"],
        "entry_type": config["entry_type"],
        "created_at": started_at,
        "operator": config["operator"],
        "permission_level": config["permission_level"],
        "git": collect_git_info(repo_root),
        "environment": {
            "host": "windows+wsl2",
            "container": "kuavo5w_sim",
            "robot": "kuavo5w",
            "simulator": "mujoco",
        },
        "artifacts": {
            "config": "config.yaml",
            "resolved_config": "resolved_config.yaml",
            "metrics": "metrics.json",
            "result": "result.json",
            "status": "status.json",
            "events": "events.jsonl",
            "stdout": "stdout.log",
            "stderr": "stderr.log",
            "command": "command.txt",
            "capabilities": "capabilities.json",
        },
    }
    write_json(episode_dir / "manifest.json", manifest)
    write_status(episode_dir, run_id, status, "finished")
    return result


def tail_text(text: str, max_lines: int = 40, max_chars: int = 4000) -> str:
    lines = (text or "").splitlines()
    tail = "\n".join(lines[-max_lines:])
    if len(tail) > max_chars:
        return tail[-max_chars:]
    return tail
