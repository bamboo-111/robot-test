#!/usr/bin/env python3
"""Read-only v0.1-alpha health checks."""

from __future__ import annotations

import http.client
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTAINER_NAME = "kuavo5w_sim"
WEB_HOST = "127.0.0.1"
WEB_PORT = 8765
TIMEOUT_SECONDS = 6
IMPORT_DIR_CANDIDATES = [
    ROOT / "kuavo_sim_platform" / "imported_scripts",
    ROOT / "imported_scripts",
    ROOT / "scripts" / "imported",
    ROOT / "uploads" / "scripts",
]


@dataclass
class CheckResult:
    name: str
    level: str
    ok: bool
    message: str
    critical: bool = True


def run_command(args: list[str], timeout: int = TIMEOUT_SECONDS) -> tuple[int, str, bool]:
    try:
        completed = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        return completed.returncode, (completed.stdout or "") + (completed.stderr or ""), False
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") + (exc.stderr or "")
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        return 124, output, True
    except OSError as exc:
        return 127, str(exc), False


def docker_exec_bash(command: str) -> list[str]:
    return ["docker", "exec", CONTAINER_NAME, "bash", "-lc", command]


def ros_bash(command: str) -> str:
    return (
        "set -o pipefail; "
        "source /root/kuavo_ws/installed/setup.bash 2>/dev/null || true; "
        "source /root/kuavo_ws/devel/setup.bash 2>/dev/null || true; "
        f"{command}"
    )


def print_result(result: CheckResult) -> None:
    print(f"[{result.level}] {result.name}: {result.message}")


def check_docker_cli() -> CheckResult:
    code, output, timed_out = run_command(["docker", "--version"])
    if timed_out:
        return CheckResult("Docker CLI", "FAIL", False, "docker --version timed out")
    if code == 0:
        return CheckResult("Docker CLI", "PASS", True, output.strip())
    return CheckResult("Docker CLI", "FAIL", False, output.strip() or "docker command failed")


def check_container_exists() -> CheckResult:
    code, output, timed_out = run_command(["docker", "ps", "-a", "--filter", f"name={CONTAINER_NAME}", "--format", "{{.Names}}"])
    if timed_out:
        return CheckResult("container exists", "FAIL", False, "docker ps timed out")
    if code != 0:
        return CheckResult("container exists", "FAIL", False, output.strip() or "docker ps failed")
    names = {line.strip() for line in output.splitlines() if line.strip()}
    if CONTAINER_NAME in names:
        return CheckResult("container exists", "PASS", True, CONTAINER_NAME)
    return CheckResult("container exists", "FAIL", False, f"{CONTAINER_NAME} not found")


def check_container_running() -> CheckResult:
    code, output, timed_out = run_command(["docker", "inspect", "-f", "{{.State.Running}}", CONTAINER_NAME])
    if timed_out:
        return CheckResult("container running", "FAIL", False, "docker inspect timed out")
    if code != 0:
        return CheckResult("container running", "FAIL", False, output.strip() or "docker inspect failed")
    if output.strip().lower() == "true":
        return CheckResult("container running", "PASS", True, "running")
    return CheckResult("container running", "FAIL", False, "not running")


def check_container_command(name: str, command: str, expected: str | None = None) -> CheckResult:
    code, output, timed_out = run_command(docker_exec_bash(ros_bash(command)))
    if timed_out:
        return CheckResult(name, "FAIL", False, "command timed out")
    if code != 0:
        return CheckResult(name, "FAIL", False, output.strip() or "command failed")
    if expected and expected not in output.splitlines():
        return CheckResult(name, "FAIL", False, f"{expected} not found")
    return CheckResult(name, "PASS", True, "ok")


def check_web_console() -> CheckResult:
    try:
        conn = http.client.HTTPConnection(WEB_HOST, WEB_PORT, timeout=TIMEOUT_SECONDS)
        conn.request("GET", "/")
        response = conn.getresponse()
        response.read(256)
        conn.close()
        if 200 <= response.status < 500:
            return CheckResult("web console", "PASS", True, f"HTTP {response.status}", critical=False)
        return CheckResult("web console", "WARN", False, f"HTTP {response.status}", critical=False)
    except OSError as exc:
        return CheckResult("web console", "WARN", False, str(exc), critical=False)


def check_import_dir() -> CheckResult:
    existing = [path for path in IMPORT_DIR_CANDIDATES if path.exists()]
    if existing:
        joined = ", ".join(str(path) for path in existing)
        return CheckResult("script import dir", "PASS", True, joined, critical=False)
    candidates = ", ".join(str(path) for path in IMPORT_DIR_CANDIDATES)
    return CheckResult("script import dir", "WARN", False, f"no candidate exists: {candidates}", critical=False)


def main() -> int:
    print("[INFO] v0.1-alpha smoke test started")
    print("[INFO] This script is read-only and does not publish control commands")

    checks = [
        check_docker_cli(),
        check_container_exists(),
        check_container_running(),
        check_container_command("rostopic available", "command -v rostopic"),
        check_container_command("rostopic list", "rostopic list"),
        check_container_command("/cmd_vel", "rostopic list", "/cmd_vel"),
        check_container_command("/mobile_manipulator_mpc_control", "rosservice list", "/mobile_manipulator_mpc_control"),
        check_web_console(),
        check_import_dir(),
    ]

    for result in checks:
        print_result(result)

    critical_failures = [result for result in checks if result.critical and not result.ok]
    warnings = [result for result in checks if result.level == "WARN"]
    print(f"[INFO] Summary: {len(checks) - len(critical_failures)} checks without critical failure, {len(critical_failures)} critical failure(s), {len(warnings)} warning(s)")

    if critical_failures:
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"[FAIL] smoke test script failed: {exc}")
        sys.exit(2)
