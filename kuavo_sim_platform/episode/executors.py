"""Episode executors."""

from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class ExecutorResult:
    exit_code: int
    ok: bool
    stdout: str
    stderr: str
    command: str
    duration_sec: float | None = None


@dataclass(frozen=True)
class SafeStopResult:
    attempted: bool
    ok: bool | None
    exit_code: int | None
    stdout: str
    stderr: str
    command: str
    duration_sec: float | None
    failure_reason: str | None
    reason: str | None = None


def powershell_executable() -> str:
    if sys.platform == "win32":
        return "powershell.exe"
    return "powershell"


def command_text(args: list[str]) -> str:
    return " ".join(args)


def scenario_command_args(config: dict, repo_root: Path) -> list[str]:
    scenario = config.get("scenario") or {}
    script_path = repo_root / "scripts" / "windows" / "start-kuavo5w-platform.ps1"
    return [
        powershell_executable(),
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script_path),
        "-Scenario",
        str(scenario.get("container_file", "")),
        "-ReadyTimeoutSeconds",
        str(scenario.get("ready_timeout_sec", 30)),
    ]


def safe_stop_command_args(repo_root: Path) -> list[str]:
    script_path = repo_root / "scripts" / "windows" / "kuavo5w-restore.ps1"
    return [
        powershell_executable(),
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script_path),
    ]


def run_command(command_args: list[str], repo_root: Path, timeout_sec: int, timeout_message: str) -> ExecutorResult:
    text_command = command_text(command_args)
    start = time.monotonic()
    try:
        completed = subprocess.run(
            command_args,
            cwd=repo_root,
            env={**os.environ, "KUAVO_TIMING": "1"},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
            check=False,
        )
        duration_sec = round(time.monotonic() - start, 3)
        return ExecutorResult(
            exit_code=completed.returncode,
            ok=completed.returncode == 0,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
            command=text_command,
            duration_sec=duration_sec,
        )
    except subprocess.TimeoutExpired as exc:
        duration_sec = round(time.monotonic() - start, 3)
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
            stderr=stderr or timeout_message,
            command=text_command,
            duration_sec=duration_sec,
        )
    except OSError as exc:
        duration_sec = round(time.monotonic() - start, 3)
        return ExecutorResult(
            exit_code=127,
            ok=False,
            stdout="",
            stderr=str(exc),
            command=text_command,
            duration_sec=duration_sec,
        )


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
    return run_command(
        command_args,
        repo_root,
        int(config.get("timeout_sec", 30)),
        f"check timed out after {config.get('timeout_sec', 30)} seconds",
    )


def run_scenario(config: dict, repo_root: Path) -> ExecutorResult:
    command_args = scenario_command_args(config, repo_root)
    return run_command(
        command_args,
        repo_root,
        int(config.get("timeout_sec", 180)),
        f"scenario timed out after {config.get('timeout_sec', 180)} seconds",
    )


def run_safe_stop(repo_root: Path, timeout_sec: int = 90) -> SafeStopResult:
    command_args = safe_stop_command_args(repo_root)
    result = run_command(
        command_args,
        repo_root,
        timeout_sec,
        f"safe stop timed out after {timeout_sec} seconds",
    )
    return SafeStopResult(
        attempted=True,
        ok=result.ok,
        exit_code=result.exit_code,
        stdout=result.stdout,
        stderr=result.stderr,
        command=result.command,
        duration_sec=result.duration_sec,
        failure_reason=None if result.ok else (result.stderr.strip() or result.stdout.strip() or f"exit_code={result.exit_code}"),
    )


def skipped_safe_stop(reason: str) -> SafeStopResult:
    return SafeStopResult(
        attempted=False,
        ok=None,
        exit_code=None,
        stdout="",
        stderr="",
        command="",
        duration_sec=None,
        failure_reason=None,
        reason=reason,
    )


def run_executor(config: dict, repo_root: Path) -> ExecutorResult:
    entry_type = config.get("entry_type")
    if entry_type == "check":
        return run_check(config, repo_root)
    if entry_type == "scenario":
        return run_scenario(config, repo_root)
    return ExecutorResult(
        exit_code=2,
        ok=False,
        stdout="",
        stderr=f"unsupported entry_type: {entry_type}",
        command="",
    )
