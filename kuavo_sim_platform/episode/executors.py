"""Episode executors."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExecutorResult:
    exit_code: int
    ok: bool
    stdout: str
    stderr: str
    command: str


def run_check(config: dict, repo_root: Path) -> ExecutorResult:
    check_name = config.get("check", {}).get("name")
    if check_name not in {"interfaces", "smoke_test"}:
        return ExecutorResult(
            exit_code=2,
            ok=False,
            stdout="",
            stderr=f"unsupported check: {check_name}",
            command="",
        )

    command_args = [sys.executable, "scripts/smoke_test.py"]
    command_text = " ".join(command_args)

    try:
        completed = subprocess.run(
            command_args,
            cwd=repo_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=int(config.get("timeout_sec", 30)),
            check=False,
        )
        return ExecutorResult(
            exit_code=completed.returncode,
            ok=completed.returncode == 0,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
            command=command_text,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        return ExecutorResult(
            exit_code=124,
            ok=False,
            stdout=stdout,
            stderr=stderr or f"check timed out after {config.get('timeout_sec', 30)} seconds",
            command=command_text,
        )
    except OSError as exc:
        return ExecutorResult(
            exit_code=127,
            ok=False,
            stdout="",
            stderr=str(exc),
            command=command_text,
        )


def run_executor(config: dict, repo_root: Path) -> ExecutorResult:
    entry_type = config.get("entry_type")
    if entry_type == "check":
        return run_check(config, repo_root)
    return ExecutorResult(
        exit_code=2,
        ok=False,
        stdout="",
        stderr=f"unsupported entry_type: {entry_type}",
        command="",
    )
