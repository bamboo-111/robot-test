#!/usr/bin/env python3
"""Local web controller for Kuavo 5-W simulation scripts."""

from __future__ import annotations

import argparse
import hashlib
import json
import locale
import os
import re
import subprocess
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = Path(__file__).resolve().parent / "static"
WINDOWS_SCRIPT = ROOT / "scripts" / "windows" / "start-kuavo5w-platform.ps1"
RESTORE_SCRIPT = ROOT / "scripts" / "windows" / "kuavo5w-restore.ps1"
SCENARIO_DIR = ROOT / "kuavo_sim_platform" / "scenarios"
IMPORTED_SCRIPT_DIR = ROOT / "kuavo_sim_platform" / "imported_scripts"
SMOKE_TEST = ROOT / "scripts" / "smoke_test.py"
ENV_SNAPSHOT = ROOT / "scripts" / "collect_env_snapshot.py"
INSPECT_INTERFACES = ROOT / "kuavo_sim_platform" / "scripts" / "inspect_interfaces.py"
INSPECT_INTERFACES_CONTAINER = "/root/kuavo_deploy/kuavo_sim_platform/scripts/inspect_interfaces.py"
SCRIPT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*\.py$")
MAX_IMPORT_BYTES = 512 * 1024
COMMAND_LOCK = threading.Lock()

SCRIPT_CATEGORIES = {
    "bc_safe_probe.py": ("diagnostic", "read-only ROS availability probe"),
    "ik_all_diag.py": ("diagnostic", "IK diagnostic sweep"),
    "ik_diag.py": ("diagnostic", "single IK diagnostic"),
    "ik_points_diag.py": ("diagnostic", "IK waypoint diagnostic"),
    "tokenless_smoke_test.py": ("import-test", "web import smoke file"),
    "web_import_smoke.py": ("import-test", "web import smoke file"),
    "desktop_salute.py": ("experiment", "desktop-exported salute action"),
    "left_ok_gesture.py": ("experiment", "left arm OK gesture"),
    "make_heart.py": ("experiment", "two-arm heart gesture"),
    "right_wave.py": ("experiment", "right-arm wave"),
    "safe_square_probe.py": ("experiment", "safe base square probe"),
    "salute_and_cruise.py": ("experiment", "combined arm and base action"),
}
HIDDEN_SCRIPT_CATEGORIES = {"import-test"}


class CommandResult(dict):
    @classmethod
    def from_completed(cls, completed: subprocess.CompletedProcess[bytes]):
        return cls(
            ok=completed.returncode == 0,
            code=completed.returncode,
            output=decode_process_output(completed.stdout, completed.stderr),
            ts=time.strftime("%Y-%m-%d %H:%M:%S"),
        )


def decode_bytes(data: bytes | None) -> str:
    if not data:
        return ""
    if len(data) >= 4:
        even_nuls = data[0::2].count(0)
        odd_nuls = data[1::2].count(0)
        half_len = max(1, len(data) // 2)
        if odd_nuls / half_len > 0.25:
            try:
                return data.decode("utf-16le")
            except UnicodeDecodeError:
                pass
        if even_nuls / half_len > 0.25:
            try:
                return data.decode("utf-16be")
            except UnicodeDecodeError:
                pass
    encodings = [
        "utf-8-sig",
        "utf-8",
        locale.getpreferredencoding(False),
        "gb18030",
        "cp936",
    ]
    seen = set()
    for encoding in encodings:
        if not encoding:
            continue
        key = encoding.lower()
        if key in seen:
            continue
        seen.add(key)
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
        except LookupError:
            continue
    return data.decode("utf-8", errors="replace")


def decode_process_output(stdout: bytes | None, stderr: bytes | None) -> str:
    return decode_bytes(stdout) + decode_bytes(stderr)


def run_command(args: list[str], timeout: int = 120) -> CommandResult:
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    completed = subprocess.run(
        args,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        env=env,
    )
    return CommandResult.from_completed(completed)


def run_serialized(fn):
    if not COMMAND_LOCK.acquire(blocking=False):
        return CommandResult(
            ok=False,
            code=409,
            output="another control command is already running",
            ts=time.strftime("%Y-%m-%d %H:%M:%S"),
        )
    try:
        return fn()
    finally:
        COMMAND_LOCK.release()


def powershell_script(script: Path, *args: str, timeout: int = 120) -> CommandResult:
    return run_command(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            *args,
        ],
        timeout=timeout,
    )


def platform(*args: str, timeout: int = 120) -> CommandResult:
    return powershell_script(WINDOWS_SCRIPT, *args, timeout=timeout)


def wsl_exec(command: str, timeout: int = 60) -> CommandResult:
    return run_command(
        [
            "wsl",
            "-d",
            "Ubuntu-20.04",
            "--",
            "docker",
            "exec",
            "kuavo5w_sim",
            "bash",
            "-lc",
            command,
        ],
        timeout=timeout,
    )


def wsl_host_exec(command: str, timeout: int = 20) -> CommandResult:
    return run_command(
        [
            "wsl",
            "-d",
            "Ubuntu-20.04",
            "--",
            "bash",
            "-lc",
            command,
        ],
        timeout=timeout,
    )


def stop_simulator_launch() -> CommandResult:
    return wsl_exec(
        r"""
set +e
kill_matching() {
  pattern="$1"
  signal="$2"
  for target in $(pgrep -f "$pattern" 2>/dev/null || true); do
    test "$target" = "$$" && continue
    test "$target" = "$PPID" && continue
    kill "$signal" "$target" 2>/dev/null || true
  done
}
if test -f /tmp/kuavo5w_mujoco.pid; then
  pid="$(cat /tmp/kuavo5w_mujoco.pid 2>/dev/null)"
  if test -n "$pid" && kill -0 "$pid" 2>/dev/null; then
    pgid="$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' ')"
    if test -n "$pgid"; then
      kill -TERM "-$pgid" 2>/dev/null || true
    fi
    kill -TERM "$pid" 2>/dev/null || true
  fi
fi
kill_matching 'start-kuavo5w-mujoco.sh' -TERM
kill_matching 'roslaunch' -TERM
kill_matching 'roscore' -TERM
kill_matching 'rosmaster' -TERM
kill_matching 'MujocoNodelet' -TERM
kill_matching 'start_node.sh' -TERM
sleep 2
kill_matching 'start-kuavo5w-mujoco.sh' -KILL
kill_matching 'roslaunch' -KILL
kill_matching 'roscore' -KILL
kill_matching 'rosmaster' -KILL
kill_matching 'MujocoNodelet' -KILL
kill_matching 'start_node.sh' -KILL
rm -f /tmp/kuavo5w_mujoco.pid
echo simulator launch stopped
ps -eo pid,ppid,stat,comm,args | grep -E 'mujoco|roslaunch|roscore|rosmaster' | grep -v grep || true
exit 0
""",
        timeout=40,
    )


def powershell_exec(command: str, timeout: int = 20) -> CommandResult:
    return run_command(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        timeout=timeout,
    )


def ssh_status() -> dict:
    wsl_script = r"""
set +e
echo '=== who ==='
who 2>/dev/null || true
echo '=== ss_22 ==='
ss -tnp 2>/dev/null | grep -E '(:22 )' || true
echo '=== listen_22 ==='
ss -tulpen 2>/dev/null | grep -E '(:22 )' || true
echo '=== sshd_ps ==='
ps -ef | grep '[s]shd' || true
echo '=== ssh_journal ==='
journalctl -u ssh --no-pager -n 60 2>/dev/null || tail -n 60 /var/log/auth.log 2>/dev/null || true
"""
    windows_script = r"""
$ErrorActionPreference = 'SilentlyContinue'
Write-Output '=== portproxy ==='
netsh interface portproxy show all
Write-Output '=== tcp_2222 ==='
Get-NetTCPConnection -LocalPort 2222 | Select-Object LocalAddress,LocalPort,RemoteAddress,RemotePort,State,OwningProcess | Format-Table -AutoSize | Out-String
Write-Output '=== sshd_local_test ==='
Test-NetConnection 127.0.0.1 -Port 2222 | Select-Object ComputerName,RemotePort,TcpTestSucceeded | Format-List | Out-String
"""
    wsl_result = wsl_host_exec(wsl_script, timeout=20)
    windows_result = powershell_exec(windows_script, timeout=20)
    return {
        "ok": bool(wsl_result.get("ok")) and bool(windows_result.get("ok")),
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "wsl": wsl_result,
        "windows": windows_result,
    }


def container_python(command: str) -> str:
    return (
        "source /root/kuavo_ws/installed/setup.bash; "
        "source /root/kuavo_ws/devel/setup.bash; "
        "export LD_LIBRARY_PATH=/opt/drake/lib:/usr/lib:${LD_LIBRARY_PATH:-}; "
        "export PYTHONPATH=/root/kuavo_ws/src/kuavo_humanoid_sdk:"
        "/root/kuavo_ws/devel/lib/python3/dist-packages:"
        "/root/kuavo_ws/installed/lib/python3/dist-packages:"
        "/opt/ros/noetic/lib/python3/dist-packages; "
        "cd /root/kuavo_deploy; "
        f"{command}"
    )


def quick_script(script_path: str) -> CommandResult:
    check = (
        "timeout 3 rostopic info /cmd_vel >/dev/null 2>&1 && "
        "timeout 3 rosservice info /mobile_manipulator_mpc_control >/dev/null 2>&1"
    )
    return wsl_exec(
        container_python(
            f"if ! ({check}); then "
            "echo 'ROS interfaces are not ready or simulator is sleeping. Click start/connect first.'; "
            "exit 2; "
            "fi; "
            f"python3 '{script_path}'"
        ),
        timeout=300,
    )


def ros_interfaces() -> CommandResult:
    return wsl_exec(container_python(f"python3 '{INSPECT_INTERFACES_CONTAINER}'"), timeout=90)


def run_host_python(script: Path, timeout: int) -> CommandResult:
    return run_command([sys.executable, str(script)], timeout=timeout)


def list_scenarios() -> list[str]:
    if not SCENARIO_DIR.exists():
        return []
    return sorted(path.name for path in SCENARIO_DIR.glob("*.yaml") if path.is_file())


def list_scripts() -> list[str]:
    if not IMPORTED_SCRIPT_DIR.exists():
        return []
    return sorted(path.name for path in IMPORTED_SCRIPT_DIR.glob("*.py") if path.is_file())


def script_info(path: Path) -> dict:
    data = path.read_bytes()
    stat = path.stat()
    digest = hashlib.sha256(data).hexdigest()
    category, description = SCRIPT_CATEGORIES.get(
        path.name, ("experiment", "imported script")
    )
    return {
        "name": path.name,
        "size": len(data),
        "mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
        "sha256": digest,
        "sha256_short": digest[:12],
        "category": category,
        "description": description,
        "visible": category not in HIDDEN_SCRIPT_CATEGORIES,
    }


def list_script_infos() -> list[dict]:
    if not IMPORTED_SCRIPT_DIR.exists():
        return []
    return [
        script_info(path)
        for path in sorted(IMPORTED_SCRIPT_DIR.glob("*.py"), key=lambda item: item.name)
        if path.is_file()
    ]


def list_visible_script_infos() -> list[dict]:
    return [info for info in list_script_infos() if info["visible"]]


def scenario_container_path(name: str) -> str:
    allowed = set(list_scenarios())
    if name not in allowed:
        raise ValueError(f"unknown scenario: {name}")
    return f"/root/kuavo_deploy/kuavo_sim_platform/scenarios/{name}"


def validate_script_name(name: str) -> str:
    if not SCRIPT_NAME_RE.fullmatch(name or ""):
        raise ValueError("script name must be an ASCII .py filename")
    return name


def script_container_path(name: str) -> str:
    name = validate_script_name(name)
    allowed = set(list_scripts())
    if name not in allowed:
        raise ValueError(f"unknown script: {name}")
    return f"/root/kuavo_deploy/kuavo_sim_platform/imported_scripts/{name}"


def import_script(name: str, content: str) -> CommandResult:
    name = validate_script_name(name)
    if not isinstance(content, str) or not content.strip():
        raise ValueError("script content is empty")
    encoded = content.encode("utf-8")
    if len(encoded) > MAX_IMPORT_BYTES:
        raise ValueError(f"script is too large; max {MAX_IMPORT_BYTES} bytes")
    IMPORTED_SCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    path = IMPORTED_SCRIPT_DIR / name
    old_hash = None
    if path.exists():
        old_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    new_hash = hashlib.sha256(encoded).hexdigest()
    changed = old_hash != new_hash
    if changed:
        path.write_text(content, encoding="utf-8", newline="\n")
    info = script_info(path)
    state = "updated" if changed and old_hash else "created" if changed else "unchanged"
    return CommandResult(
        ok=True,
        code=0,
        output=(
            f"imported script: {path}\n"
            f"state: {state}\n"
            f"changed: {str(changed).lower()}\n"
            f"size: {info['size']} bytes\n"
            f"mtime: {info['mtime']}\n"
            f"sha256: {info['sha256']}"
        ),
        ts=time.strftime("%Y-%m-%d %H:%M:%S"),
        script=info,
        changed=changed,
        previous_sha256=old_hash,
    )


def action(name: str, params: dict[str, list[str]]) -> CommandResult:
    if name == "status":
        return platform("-ReadyTimeoutSeconds", "10", timeout=40)
    if name == "connect":
        return platform("-VisualizeHumanoid", "-ReadyTimeoutSeconds", "30", timeout=90)
    if name == "connect_gui":
        return platform("-VisualizeHumanoid", "-ReadyTimeoutSeconds", "30", timeout=90)
    if name == "connect_headless":
        return platform("-ReadyTimeoutSeconds", "30", timeout=90)
    if name == "backend_check":
        return platform("-ReadyTimeoutSeconds", "10", timeout=40)
    if name == "probe":
        return platform("-RunProbe", "-ReadyTimeoutSeconds", "30", timeout=120)
    if name == "forward":
        return platform("-Demo", "forward", "-ReadyTimeoutSeconds", "30", timeout=120)
    if name == "restore":
        return powershell_script(RESTORE_SCRIPT, timeout=90)
    if name == "pause":
        return wsl_exec(
            "source /root/kuavo_ws/installed/setup.bash; "
            "source /root/kuavo_ws/devel/setup.bash; "
            "rosservice call /mobile_manipulator_mpc_pause_resume 'pause: true'",
            timeout=30,
        )
    if name == "resume":
        return wsl_exec(
            "source /root/kuavo_ws/installed/setup.bash; "
            "source /root/kuavo_ws/devel/setup.bash; "
            "rosservice call /mobile_manipulator_mpc_pause_resume 'pause: false'",
            timeout=30,
        )
    if name == "sleep":
        return stop_simulator_launch()
    if name == "stop_sim":
        return action("sleep", params)
    if name == "log":
        return wsl_exec("tail -120 /tmp/kuavo5w_mujoco_start.log", timeout=30)
    if name == "smoke_test":
        return run_host_python(SMOKE_TEST, timeout=90)
    if name == "env_snapshot":
        return run_host_python(ENV_SNAPSHOT, timeout=120)
    if name == "interfaces":
        return ros_interfaces()
    if name == "scenario":
        scenario = (
            (params.get("scenario") or [""])[0]
            or (params.get("file") or [""])[0]
            or (params.get("name") or [""])[0]
        )
        return platform(
            "-Scenario",
            scenario_container_path(scenario),
            "-ReadyTimeoutSeconds",
            "30",
            timeout=180,
        )
    if name == "script":
        script = (params.get("script") or [""])[0]
        return platform(
            "-Script",
            script_container_path(script),
            "-ReadyTimeoutSeconds",
            "30",
            timeout=300,
        )
    if name == "script_fast":
        script = (params.get("script") or [""])[0]
        return quick_script(script_container_path(script))
    return CommandResult(ok=False, code=400, output=f"unknown action: {name}", ts=time.strftime("%Y-%m-%d %H:%M:%S"))


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/scenarios":
            self.send_json({"scenarios": list_scenarios()})
            return
        if parsed.path == "/api/scripts":
            all_infos = list_script_infos()
            infos = [item for item in all_infos if item["visible"]]
            self.send_json({"scripts": [item["name"] for item in infos], "script_info": infos})
            return
        if parsed.path == "/api/scripts/all":
            infos = list_script_infos()
            self.send_json({"scripts": [item["name"] for item in infos], "script_info": infos})
            return
        if parsed.path == "/api/ssh/status":
            self.send_json(ssh_status())
            return
        if parsed.path == "/api/action":
            query = parse_qs(parsed.query)
            name = (query.get("name") or [""])[0]
            try:
                result = run_serialized(lambda: action(name, query))
                self.send_json(result, status=409 if result.get("code") == 409 else 200)
            except Exception as exc:
                self.send_json(
                    {
                        "ok": False,
                        "code": 500,
                        "output": f"{type(exc).__name__}: {exc}",
                        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                    },
                    status=500,
                )
            return
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/scripts/import":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0:
                    raise ValueError("empty request body")
                if length > MAX_IMPORT_BYTES + 4096:
                    raise ValueError(f"request is too large; max {MAX_IMPORT_BYTES} bytes")
                raw = self.rfile.read(length).decode("utf-8")
                payload = json.loads(raw)
                result = run_serialized(lambda: import_script(payload.get("name", ""), payload.get("content", "")))
                self.send_json(result)
            except Exception as exc:
                self.send_json(
                    {
                        "ok": False,
                        "code": 400,
                        "output": f"{type(exc).__name__}: {exc}",
                        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                    },
                    status=400,
                )
            return
        self.send_json(
            {
                "ok": False,
                "code": 404,
                "output": f"unknown endpoint: {parsed.path}",
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            },
            status=404,
        )


def main(argv=None):
    parser = argparse.ArgumentParser(description="Start Kuavo 5-W web control")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)

    if not WINDOWS_SCRIPT.exists():
        print(f"missing script: {WINDOWS_SCRIPT}", file=sys.stderr)
        return 1
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Kuavo web control: http://{args.host}:{args.port}")
    print("Press Ctrl+C to stop the web server.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
