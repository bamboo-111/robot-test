#!/usr/bin/env python3
"""Read-only ROS availability probe for B/C web-console testing."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass


TIMEOUT_SECONDS = 5
REQUIRED_TOPIC = "/cmd_vel"
REQUIRED_SERVICE = "/mobile_manipulator_mpc_control"


@dataclass
class CommandResult:
    code: int
    output: str
    timed_out: bool = False


def run_command(args: list[str], timeout: int = TIMEOUT_SECONDS) -> CommandResult:
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
        return CommandResult(
            code=completed.returncode,
            output=(completed.stdout or "") + (completed.stderr or ""),
        )
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") + (exc.stderr or "")
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        return CommandResult(code=124, output=output, timed_out=True)
    except OSError as exc:
        return CommandResult(code=127, output=str(exc))


def print_block(prefix: str, text: str) -> None:
    clean = text.strip()
    if clean:
        print(f"{prefix} {clean}")


def check_rostopic_list() -> tuple[int, list[str]]:
    result = run_command(["rostopic", "list"])
    if result.timed_out:
        print("[FAIL] rostopic list timed out")
        print_block("[INFO]", result.output)
        return 2, []
    if result.code != 0:
        print("[FAIL] rostopic list failed")
        print_block("[INFO]", result.output)
        return 1, []

    topics = [line.strip() for line in result.output.splitlines() if line.strip()]
    print("[PASS] rostopic list succeeded")
    return 0, topics


def check_topic(topic: str, topics: list[str]) -> int:
    if topic in topics:
        print(f"[PASS] {topic} found")
        return 0

    result = run_command(["rostopic", "info", topic])
    if result.timed_out:
        print(f"[FAIL] rostopic info {topic} timed out")
        return 2
    if result.code == 0:
        print(f"[PASS] {topic} found")
        return 0

    print(f"[FAIL] {topic} not found")
    print_block("[INFO]", result.output)
    return 1


def check_service(service: str) -> int:
    result = run_command(["rosservice", "info", service])
    if result.timed_out:
        print(f"[FAIL] rosservice info {service} timed out")
        return 2
    if result.code == 0:
        print(f"[PASS] {service} found")
        return 0

    print(f"[FAIL] {service} not found")
    print_block("[INFO]", result.output)
    return 1


def main() -> int:
    print("[INFO] BC safe probe started")
    print("[INFO] This probe is read-only and does not publish /cmd_vel")

    list_code, topics = check_rostopic_list()
    if list_code != 0:
        return list_code

    results = [
        check_topic(REQUIRED_TOPIC, topics),
        check_service(REQUIRED_SERVICE),
    ]
    if any(code == 2 for code in results):
        return 2
    if any(code != 0 for code in results):
        return 1

    print("[INFO] Probe completed successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())

