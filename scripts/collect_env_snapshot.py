#!/usr/bin/env python3
"""Collect a read-only v0.1-alpha environment snapshot."""

from __future__ import annotations

import datetime as _dt
import platform
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_ROOT = ROOT / "docs" / "env_snapshots"
CONTAINER_NAME = "kuavo5w_sim"
TIMEOUT_SECONDS = 12


@dataclass
class SnapshotCommand:
    name: str
    filename: str
    args: list[str]
    timeout: int = TIMEOUT_SECONDS


@dataclass
class SnapshotResult:
    name: str
    filename: str
    code: int
    timed_out: bool
    output: str


def run_command(command: SnapshotCommand) -> SnapshotResult:
    try:
        completed = subprocess.run(
            command.args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=command.timeout,
            check=False,
        )
        output = (completed.stdout or "") + (completed.stderr or "")
        return SnapshotResult(command.name, command.filename, completed.returncode, False, output)
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") + (exc.stderr or "")
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        return SnapshotResult(command.name, command.filename, 124, True, output)
    except OSError as exc:
        return SnapshotResult(command.name, command.filename, 127, False, str(exc))


def docker_exec_bash(command: str) -> list[str]:
    return ["docker", "exec", CONTAINER_NAME, "bash", "-lc", command]


def ros_bash(command: str) -> str:
    return (
        "set -o pipefail; "
        "source /root/kuavo_ws/installed/setup.bash 2>/dev/null || true; "
        "source /root/kuavo_ws/devel/setup.bash 2>/dev/null || true; "
        f"{command}"
    )


def build_commands() -> list[SnapshotCommand]:
    return [
        SnapshotCommand("uname", "uname.txt", ["uname", "-a"]),
        SnapshotCommand("host_python", "python_version.txt", [sys.executable, "--version"]),
        SnapshotCommand("docker_ps_a", "docker_ps_a.txt", ["docker", "ps", "-a"]),
        SnapshotCommand("docker_images", "docker_images.txt", ["docker", "images"]),
        SnapshotCommand(
            "docker_inspect_kuavo5w_sim",
            "docker_inspect_kuavo5w_sim.json",
            ["docker", "inspect", CONTAINER_NAME],
        ),
        SnapshotCommand(
            "container_ros_distro",
            "container_ros_distro.txt",
            docker_exec_bash('echo "${ROS_DISTRO:-unknown}"'),
        ),
        SnapshotCommand(
            "container_python",
            "container_python_version.txt",
            docker_exec_bash("python3 --version"),
        ),
        SnapshotCommand(
            "ros_topics",
            "ros_topics.txt",
            docker_exec_bash(ros_bash("rostopic list | sort")),
        ),
    ]


def write_summary(snapshot_dir: Path, results: list[SnapshotResult]) -> None:
    lines = [
        "# v0.1-alpha 环境快照",
        "",
        f"- 生成时间：{_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 项目目录：{ROOT}",
        f"- 主机系统：{platform.platform()}",
        f"- Python：{sys.version.split()[0]}",
        f"- Docker 容器：{CONTAINER_NAME}",
        "",
        "## 命令结果",
        "",
        "| 项目 | 文件 | 结果 |",
        "|---|---|---|",
    ]
    for result in results:
        if result.timed_out:
            status = "TIMEOUT"
        elif result.code == 0:
            status = "OK"
        else:
            status = f"FAILED({result.code})"
        lines.append(f"| {result.name} | `{result.filename}` | {status} |")

    lines.extend(
        [
            "",
            "说明：本脚本只采集状态，不启动、停止或修改 Docker/ROS/WSL。部分命令失败时，请查看对应输出文件。",
            "",
        ]
    )
    (snapshot_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    timestamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot_dir = SNAPSHOT_ROOT / f"env_snapshot_{timestamp}"
    snapshot_dir.mkdir(parents=True, exist_ok=False)

    print(f"[INFO] Writing environment snapshot to {snapshot_dir}")
    results: list[SnapshotResult] = []
    for command in build_commands():
        print(f"[INFO] Collecting {command.name}")
        result = run_command(command)
        results.append(result)
        (snapshot_dir / command.filename).write_text(result.output, encoding="utf-8")
        if result.timed_out:
            print(f"[WARN] {command.name} timed out")
        elif result.code != 0:
            print(f"[WARN] {command.name} failed with code {result.code}")
        else:
            print(f"[PASS] {command.name}")

    write_summary(snapshot_dir, results)
    print("[INFO] Snapshot completed")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"[FAIL] Snapshot script failed: {exc}")
        sys.exit(2)
