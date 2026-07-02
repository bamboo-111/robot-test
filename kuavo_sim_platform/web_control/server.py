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

# ---------------------------------------------------------------------------
# episode / artifact / experiment whitelists (C 任务)
# ---------------------------------------------------------------------------
EPISODE_OUTPUTS_DIR = ROOT / "outputs" / "episodes"
RUN_INDEX_PATH = ROOT / "outputs" / "run_index.jsonl"
RUN_EPISODE_SCRIPT = ROOT / "scripts" / "run_episode.py"

ARTIFACT_WHITELIST = {
    "manifest.json",
    "metrics.json",
    "result.json",
    "status.json",
    "events.jsonl",
    "latency_breakdown.json",
    "external_timing.json",
    "safe_stop.json",
    "stdout.log",
    "stderr.log",
}

# experiment 显示名 -> repo-relative config 路径
EXPERIMENT_CONFIG_MAP = {
    "fast_health_check": "configs/experiments/fast_health_check.yaml",
    "read_only_interfaces": "configs/experiments/read_only_interfaces.yaml",
    "full_interfaces_check": "configs/experiments/full_interfaces_check.yaml",
}
BASE_PROBE_KEY = "base_probe"
BASE_PROBE_LABEL = "base_probe (需 A 确认)"
BASE_PROBE_CONFIG = "configs/experiments/base_probe.yaml"

RUN_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
OPERATOR_RE = re.compile(r"^[A-Za-z0-9_.-]{1,32}$")
MAX_EPISODE_RUN_BYTES = 4096


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


# ---------------------------------------------------------------------------
# episode helpers (C 任务)
# ---------------------------------------------------------------------------


def _validate_run_id(run_id: str) -> str:
    if not run_id or not RUN_ID_RE.fullmatch(run_id):
        raise ValueError("invalid run_id")
    return run_id


def _episode_dir(run_id: str) -> Path:
    run_id = _validate_run_id(run_id)
    ep_dir = EPISODE_OUTPUTS_DIR / run_id
    if not ep_dir.exists() or not ep_dir.is_dir():
        raise FileNotFoundError(f"episode not found: {run_id}")
    try:
        ep_dir.resolve().relative_to(EPISODE_OUTPUTS_DIR.resolve())
    except ValueError:
        raise ValueError("invalid run_id: path escape")
    return ep_dir


def list_recent_episodes(limit: int = 20) -> list[dict]:
    episodes: list[dict] = []
    if not RUN_INDEX_PATH.exists():
        return episodes

    with RUN_INDEX_PATH.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                episodes.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    episodes.reverse()
    episodes = episodes[:limit]

    for ep in episodes:
        run_id = str(ep.get("run_id") or "")
        ep_dir = EPISODE_OUTPUTS_DIR / run_id

        latency_path = ep_dir / "latency_breakdown.json"
        if latency_path.exists():
            ep["latency_breakdown_path"] = "latency_breakdown.json"
            try:
                latency = json.loads(latency_path.read_text(encoding="utf-8", errors="replace"))
                ep["external_timing_available"] = bool(latency.get("external_timing_available"))
            except Exception:
                ep["external_timing_available"] = False
        else:
            ep["latency_breakdown_path"] = None
            ep["external_timing_available"] = False

        safe_stop_path = ep_dir / "safe_stop.json"
        if safe_stop_path.exists():
            try:
                ss = json.loads(safe_stop_path.read_text(encoding="utf-8", errors="replace"))
                ep["safe_stop_ok"] = ss.get("ok")
            except Exception:
                ep["safe_stop_ok"] = None
        else:
            ep["safe_stop_ok"] = None

    return episodes


def get_episode_detail(run_id: str) -> dict:
    ep_dir = _episode_dir(run_id)

    detail: dict = {
        "run_id": run_id,
        "episode_dir": str(ep_dir.relative_to(ROOT)),
        "artifacts": [],
    }

    for name in sorted(ARTIFACT_WHITELIST):
        artifact_path = ep_dir / name
        if artifact_path.exists() and artifact_path.is_file():
            detail["artifacts"].append({
                "name": name,
                "size": artifact_path.stat().st_size,
            })

    metrics_path = ep_dir / "metrics.json"
    if metrics_path.exists():
        try:
            detail["metrics"] = json.loads(metrics_path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            detail["metrics"] = None
    else:
        detail["metrics"] = None

    result_path = ep_dir / "result.json"
    if result_path.exists():
        try:
            detail["result"] = json.loads(result_path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            detail["result"] = None
    else:
        detail["result"] = None

    return detail


def read_artifact(run_id: str, artifact_name: str) -> dict:
    if artifact_name not in ARTIFACT_WHITELIST:
        raise ValueError(f"artifact not in whitelist: {artifact_name}")

    ep_dir = _episode_dir(run_id)
    artifact_path = ep_dir / artifact_name

    try:
        artifact_path.resolve().relative_to(ep_dir.resolve())
    except ValueError:
        raise ValueError("invalid artifact name: path escape")

    if not artifact_path.exists() or not artifact_path.is_file():
        raise FileNotFoundError(f"artifact not found: {artifact_name}")

    raw = artifact_path.read_text(encoding="utf-8", errors="replace")

    if artifact_name.endswith(".json"):
        try:
            return {"name": artifact_name, "type": "json", "content": json.loads(raw)}
        except json.JSONDecodeError:
            return {"name": artifact_name, "type": "text", "content": raw}
    elif artifact_name.endswith(".jsonl"):
        lines = [
            json.loads(l)
            for l in raw.splitlines()
            if l.strip()
        ]
        return {"name": artifact_name, "type": "jsonl", "content": lines}
    else:
        return {"name": artifact_name, "type": "text", "content": raw}


def _run_episode_subprocess(config_rel: str, operator: str) -> CommandResult:
    config_path = ROOT / config_rel
    if not config_path.exists():
        return CommandResult(
            ok=False,
            code=404,
            output=f"config file not found: {config_rel}",
            ts=time.strftime("%Y-%m-%d %H:%M:%S"),
        )
    try:
        config_path.resolve().relative_to(ROOT.resolve())
    except ValueError:
        return CommandResult(
            ok=False,
            code=400,
            output=f"config path escapes repo root: {config_rel}",
            ts=time.strftime("%Y-%m-%d %H:%M:%S"),
        )

    result = run_command(
        [
            sys.executable,
            str(RUN_EPISODE_SCRIPT),
            "--config", str(config_path),
            "--operator", operator,
        ],
        timeout=300,
    )

    output_text = result.get("output") or ""
    run_id = None
    for line in output_text.splitlines():
        if "episode created:" in line:
            for sep in ("episodes/", "episodes\\"):
                if sep in line:
                    run_id = line.split(sep, 1)[-1].strip()
                    break
            break

    result["run_id"] = run_id
    return result


def list_available_experiments() -> list[dict]:
    experiments: list[dict] = []
    for name, config_rel in EXPERIMENT_CONFIG_MAP.items():
        config_exists = (ROOT / config_rel).exists()
        experiments.append({
            "name": name,
            "config": config_rel,
            "available": config_exists,
            "enabled": True,
        })
    experiments.append({
        "name": BASE_PROBE_KEY,
        "label": BASE_PROBE_LABEL,
        "config": BASE_PROBE_CONFIG,
        "available": (ROOT / BASE_PROBE_CONFIG).exists(),
        "enabled": False,
        "disabled_reason": "需要 A 确认",
    })
    return experiments


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
        if parsed.path == "/api/experiments":
            self.send_json({"experiments": list_available_experiments()})
            return
        # /api/episodes                -> list
        # /api/episodes/<run_id>       -> detail
        # /api/episodes/<run_id>/artifact?name=... -> artifact
        if parsed.path == "/api/episodes" or parsed.path == "/api/episodes/":
            try:
                self.send_json({"episodes": list_recent_episodes()})
            except Exception as exc:
                self.send_json(
                    {"ok": False, "code": 500, "output": f"{type(exc).__name__}: {exc}"},
                    status=500,
                )
            return

        ep_match = re.match(r"^/api/episodes/([^/]+)(?:/artifact)?$", parsed.path)
        if ep_match:
            run_id = ep_match.group(1)
            if run_id == "run":
                self.send_json(
                    {"ok": False, "code": 405, "output": "use POST /api/episodes/run"},
                    status=405,
                )
                return
            if "/artifact" in parsed.path:
                query = parse_qs(parsed.query)
                artifact_name = (query.get("name") or [""])[0]
                try:
                    self.send_json(read_artifact(run_id, artifact_name))
                except (ValueError, FileNotFoundError) as exc:
                    self.send_json(
                        {"ok": False, "code": 400, "output": str(exc)},
                        status=400,
                    )
                except Exception as exc:
                    self.send_json(
                        {"ok": False, "code": 500, "output": f"{type(exc).__name__}: {exc}"},
                        status=500,
                    )
                return
            else:
                try:
                    self.send_json(get_episode_detail(run_id))
                except (ValueError, FileNotFoundError) as exc:
                    self.send_json(
                        {"ok": False, "code": 404, "output": str(exc)},
                        status=404,
                    )
                except Exception as exc:
                    self.send_json(
                        {"ok": False, "code": 500, "output": f"{type(exc).__name__}: {exc}"},
                        status=500,
                    )
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
        if parsed.path == "/api/episodes/run":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0:
                    raise ValueError("empty request body")
                if length > MAX_EPISODE_RUN_BYTES:
                    raise ValueError(f"request body too large; max {MAX_EPISODE_RUN_BYTES} bytes")
                raw = self.rfile.read(length).decode("utf-8")
                payload = json.loads(raw)
                experiment = str(payload.get("experiment", "")).strip()
                operator = str(payload.get("operator", "")).strip()

                if not experiment:
                    raise ValueError("experiment is required")
                if not operator:
                    raise ValueError("operator is required")
                if not OPERATOR_RE.fullmatch(operator):
                    raise ValueError("operator must match ^[A-Za-z0-9_.-]{1,32}$")

                config_rel: str
                if experiment == BASE_PROBE_KEY:
                    raise ValueError(
                        "base_probe 不在第一批 Web episode runner 白名单中。运动任务需 A 直接执行。"
                    )
                if experiment in EXPERIMENT_CONFIG_MAP:
                    config_rel = EXPERIMENT_CONFIG_MAP[experiment]
                else:
                    raise ValueError(f"experiment not whitelisted: {experiment}")

                result = run_serialized(lambda: _run_episode_subprocess(config_rel, operator))
                status_code = 409 if result.get("code") == 409 else 200
                self.send_json(result, status=status_code)
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
