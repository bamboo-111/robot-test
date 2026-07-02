import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from kuavo_sim_platform.episode import artifacts, runner
from kuavo_sim_platform.episode.executors import (
    ExecutorResult,
    SafeStopResult,
    run_command,
    safe_stop_command_args,
    scenario_command_args,
)
from kuavo_sim_platform.episode.external_timing import parse_external_timing
ANALYZE_SCRIPT = REPO_ROOT / "scripts" / "analyze_episode_latency.py"
analyze_spec = importlib.util.spec_from_file_location("analyze_episode_latency", ANALYZE_SCRIPT)
analyze_episode_latency = importlib.util.module_from_spec(analyze_spec)
assert analyze_spec.loader is not None
analyze_spec.loader.exec_module(analyze_episode_latency)
from kuavo_sim_platform.episode.policy import PolicyError, check_policy
from kuavo_sim_platform.episode.schema import ConfigError, resolve_config


def make_repo(tmp_path: Path) -> Path:
    repo_root = tmp_path / "repo"
    scenario_dir = repo_root / "kuavo_sim_platform" / "scenarios"
    scenario_dir.mkdir(parents=True)
    (scenario_dir / "base_probe.yaml").write_text(
        "name: base_probe\nsteps:\n  - action: stop_base\n",
        encoding="utf-8",
    )
    (scenario_dir / "base_forward.yaml").write_text(
        "name: base_forward\nsteps:\n  - action: stop_base\n",
        encoding="utf-8",
    )
    policy_dir = repo_root / "configs" / "policies"
    policy_dir.mkdir(parents=True)
    (policy_dir / "v0.2_policy.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": "0.2",
                "roles": {
                    "A": {
                        "allow_entry_types": ["check", "scenario", "script", "builtin_action"],
                        "allow_motion": True,
                        "allowed_tasks": "*",
                    },
                    "B": {
                        "allow_entry_types": ["check", "scenario"],
                        "allow_motion": True,
                        "allowed_tasks": ["read_only_interfaces", "base_probe"],
                    },
                    "C": {
                        "allow_entry_types": ["check", "scenario"],
                        "allow_motion": True,
                        "allowed_tasks": ["read_only_interfaces", "base_probe"],
                    },
                },
                "scenario_whitelist": ["kuavo_sim_platform/scenarios/base_probe.yaml"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (repo_root / "scripts" / "windows").mkdir(parents=True)
    return repo_root


def scenario_config(**overrides):
    config = {
        "schema_version": "0.2",
        "task_name": "base_probe",
        "entry_type": "scenario",
        "operator": "A",
        "permission_level": "bc_safe",
        "timeout_sec": 180,
        "safety": {
            "require_preflight": True,
            "safe_stop_on_exit": True,
            "allow_motion": True,
        },
        "scenario": {
            "file": "kuavo_sim_platform/scenarios/base_probe.yaml",
            "container_root": "/root/kuavo_deploy",
            "ready_timeout_sec": 30,
        },
        "success_criteria": {"type": "exit_code_zero"},
    }
    for key, value in overrides.items():
        config[key] = value
    return config


def check_config(**overrides):
    config = {
        "schema_version": "0.2",
        "task_name": "read_only_interfaces",
        "entry_type": "check",
        "operator": "A",
        "permission_level": "read_only",
        "timeout_sec": 30,
        "check": {"name": "interfaces"},
        "success_criteria": {"type": "exit_code_zero"},
    }
    for key, value in overrides.items():
        config[key] = value
    return config


def test_resolves_scenario_container_path(tmp_path):
    repo_root = make_repo(tmp_path)
    resolved = resolve_config(scenario_config(), repo_root)

    assert resolved["entry_type"] == "scenario"
    assert resolved["scenario"]["file"] == "kuavo_sim_platform/scenarios/base_probe.yaml"
    assert resolved["scenario"]["container_file"] == (
        "/root/kuavo_deploy/kuavo_sim_platform/scenarios/base_probe.yaml"
    )
    assert Path(resolved["scenario"]["abs_file"]).is_file()


@pytest.mark.parametrize(
    "scenario_file",
    [
        "../../danger.yaml",
        "C:\\somewhere\\danger.yaml",
        "/tmp/danger.yaml",
    ],
)
def test_rejects_unsafe_scenario_paths(tmp_path, scenario_file):
    repo_root = make_repo(tmp_path)
    config = scenario_config(
        scenario={
            "file": scenario_file,
            "container_root": "/root/kuavo_deploy",
            "ready_timeout_sec": 30,
        }
    )

    with pytest.raises(ConfigError):
        resolve_config(config, repo_root)


def test_rejects_non_whitelisted_scenario(tmp_path):
    repo_root = make_repo(tmp_path)
    config = scenario_config(
        scenario={
            "file": "kuavo_sim_platform/scenarios/base_forward.yaml",
            "container_root": "/root/kuavo_deploy",
            "ready_timeout_sec": 30,
        }
    )

    with pytest.raises(ConfigError, match="not whitelisted"):
        resolve_config(config, repo_root)


def test_bc_unknown_task_still_rejected(tmp_path):
    repo_root = make_repo(tmp_path)
    resolved = resolve_config(scenario_config(task_name="unknown_probe", operator="B"), repo_root)
    policy = yaml.safe_load((repo_root / "configs/policies/v0.2_policy.yaml").read_text(encoding="utf-8"))

    with pytest.raises(PolicyError, match="may not run task"):
        check_policy(resolved, policy)


def test_scenario_and_safe_stop_command_args(tmp_path):
    repo_root = make_repo(tmp_path)
    resolved = resolve_config(scenario_config(), repo_root)

    scenario_args = scenario_command_args(resolved, repo_root)
    safe_stop_args = safe_stop_command_args(repo_root)

    assert scenario_args[1:6] == [
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(repo_root / "scripts" / "windows" / "start-kuavo5w-platform.ps1"),
    ]
    assert "-Scenario" in scenario_args
    assert "/root/kuavo_deploy/kuavo_sim_platform/scenarios/base_probe.yaml" in scenario_args
    assert safe_stop_args[1:6] == [
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(repo_root / "scripts" / "windows" / "kuavo5w-restore.ps1"),
    ]


def test_scenario_episode_writes_safe_stop_artifacts_without_running_commands(tmp_path, monkeypatch):
    repo_root = make_repo(tmp_path)
    config_path = repo_root / "base_probe.yaml"
    config_path.write_text(yaml.safe_dump(scenario_config(), sort_keys=False), encoding="utf-8")

    monkeypatch.setattr(
        runner,
        "run_executor",
        lambda config, root: ExecutorResult(
            exit_code=3,
            ok=False,
            stdout=(
                "scenario stdout\n"
                "[TIMING] source=powershell phase=ps_script_start t_ms=1000\n"
                "[TIMING] source=powershell phase=ps_script_end t_ms=2200\n"
            ),
            stderr="scenario failed",
            command="mock scenario command",
            duration_sec=1.23,
        ),
    )
    monkeypatch.setattr(
        runner,
        "run_safe_stop",
        lambda root: SafeStopResult(
            attempted=True,
            ok=True,
            exit_code=0,
            stdout="[TIMING] source=restore phase=restore_script_start t_ms=3000\nsafe stdout\n",
            stderr="",
            command="mock safe stop command",
            duration_sec=0.12,
            failure_reason=None,
        ),
    )
    monkeypatch.setattr(runner, "collect_capabilities", lambda root: {"schema_version": "0.2", "can_run_check": True})
    monkeypatch.setattr(artifacts, "collect_git_info", lambda root: {"commit": None, "branch": None, "dirty": None})

    result = runner.run_episode(config_path, repo_root=repo_root)
    episode_dir = result.episode_dir

    assert result.ok is False
    assert (episode_dir / "scenario.yaml").read_text(encoding="utf-8").startswith("name: base_probe")
    safe_stop_stdout = (episode_dir / "safe_stop_stdout.log").read_text(encoding="utf-8")
    assert "safe stdout" in safe_stop_stdout
    assert "[TIMING] source=restore" in safe_stop_stdout
    assert (episode_dir / "safe_stop_stderr.log").read_text(encoding="utf-8") == ""

    safe_stop = json.loads((episode_dir / "safe_stop.json").read_text(encoding="utf-8"))
    assert safe_stop["attempted"] is True
    assert safe_stop["ok"] is True
    assert safe_stop["exit_code"] == 0

    metrics = json.loads((episode_dir / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["ok"] is False
    assert metrics["success"] is False
    assert metrics["safe_stop_attempted"] is True
    assert metrics["safe_stop_ok"] is True
    assert metrics["safe_stop_exit_code"] == 0
    assert metrics["scenario_path"] == "scenario.yaml"
    assert metrics["latency_breakdown_path"] == "latency_breakdown.json"
    assert metrics["external_timing_path"] == "external_timing.json"

    manifest = json.loads((episode_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["artifacts"]["scenario"] == "scenario.yaml"
    assert manifest["artifacts"]["safe_stop"] == "safe_stop.json"
    assert manifest["artifacts"]["safe_stop_stdout"] == "safe_stop_stdout.log"
    assert manifest["artifacts"]["latency_breakdown"] == "latency_breakdown.json"
    assert manifest["artifacts"]["external_timing"] == "external_timing.json"

    latency = json.loads((episode_dir / "latency_breakdown.json").read_text(encoding="utf-8"))
    assert latency["schema_version"] == "0.2"
    assert latency["entry_type"] == "scenario"
    assert latency["executor_total_ms"] is not None
    assert latency["main_command_ms"] == 1230.0
    assert latency["scenario_command_ms"] == 1230.0
    assert latency["powershell_command_ms"] == 1230.0
    assert latency["safe_stop_total_ms"] is not None
    assert latency["safe_stop_command_ms"] == 120.0
    assert latency["safe_stop_artifact_write_ms"] is not None
    assert latency["external_timing_path"] == "external_timing.json"
    assert latency["external_timing_available"] is True

    external = json.loads((episode_dir / "external_timing.json").read_text(encoding="utf-8"))
    assert external["available"] is True
    assert external["marker_count"] == 3
    assert external["durations_ms"]["powershell.ps_script_ms"] == 1200.0

    events = (episode_dir / "events.jsonl").read_text(encoding="utf-8")
    assert '"stage": "scenario_start"' in events
    assert '"stage": "scenario_end"' in events
    assert '"stage": "safe_stop_start"' in events
    assert '"stage": "safe_stop_end"' in events


def test_check_episode_writes_latency_breakdown_without_running_commands(tmp_path, monkeypatch):
    repo_root = make_repo(tmp_path)
    config_path = repo_root / "read_only_interfaces.yaml"
    config_path.write_text(yaml.safe_dump(check_config(), sort_keys=False), encoding="utf-8")

    monkeypatch.setattr(
        runner,
        "run_executor",
        lambda config, root: ExecutorResult(
            exit_code=0,
            ok=True,
            stdout="check stdout",
            stderr="",
            command="mock check command",
            duration_sec=0.45,
        ),
    )
    monkeypatch.setattr(runner, "collect_capabilities", lambda root: {"schema_version": "0.2", "can_run_check": True})
    monkeypatch.setattr(artifacts, "collect_git_info", lambda root: {"commit": None, "branch": None, "dirty": None})

    result = runner.run_episode(config_path, repo_root=repo_root)
    episode_dir = result.episode_dir

    metrics = json.loads((episode_dir / "metrics.json").read_text(encoding="utf-8"))
    manifest = json.loads((episode_dir / "manifest.json").read_text(encoding="utf-8"))
    latency = json.loads((episode_dir / "latency_breakdown.json").read_text(encoding="utf-8"))

    assert result.ok is True
    assert metrics["latency_breakdown_path"] == "latency_breakdown.json"
    assert metrics["external_timing_path"] == "external_timing.json"
    assert manifest["artifacts"]["latency_breakdown"] == "latency_breakdown.json"
    assert manifest["artifacts"]["external_timing"] == "external_timing.json"
    assert latency["schema_version"] == "0.2"
    assert latency["entry_type"] == "check"
    assert latency["executor_total_ms"] is not None
    assert latency["main_command_ms"] == 450.0
    assert latency["check_command_ms"] == 450.0
    assert latency["scenario_command_ms"] is None
    assert latency["powershell_command_ms"] is None
    assert latency["safe_stop_total_ms"] is None
    assert latency["safe_stop_command_ms"] is None
    assert latency["external_timing_available"] is False


def test_scenario_safe_stop_skipped_has_null_safe_stop_timing(tmp_path, monkeypatch):
    repo_root = make_repo(tmp_path)
    config_path = repo_root / "base_probe.yaml"
    config = scenario_config(safety={"require_preflight": True, "safe_stop_on_exit": False, "allow_motion": False})
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    monkeypatch.setattr(
        runner,
        "run_executor",
        lambda config, root: ExecutorResult(
            exit_code=0,
            ok=True,
            stdout="scenario stdout",
            stderr="",
            command="mock scenario command",
            duration_sec=0.2,
        ),
    )
    monkeypatch.setattr(runner, "collect_capabilities", lambda root: {"schema_version": "0.2", "can_run_check": True})
    monkeypatch.setattr(artifacts, "collect_git_info", lambda root: {"commit": None, "branch": None, "dirty": None})

    result = runner.run_episode(config_path, repo_root=repo_root)
    latency = json.loads((result.episode_dir / "latency_breakdown.json").read_text(encoding="utf-8"))

    assert latency["safe_stop_total_ms"] is None
    assert latency["safe_stop_command_ms"] is None
    assert latency["safe_stop_artifact_write_ms"] is None


def test_run_command_timeout_records_duration(tmp_path, monkeypatch):
    def raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=1, output="partial stdout", stderr="")

    monkeypatch.setattr(subprocess, "run", raise_timeout)

    result = run_command(["mock"], tmp_path, 1, "mock timed out")

    assert result.exit_code == 124
    assert result.ok is False
    assert result.stdout == "partial stdout"
    assert result.stderr == "mock timed out"
    assert result.duration_sec is not None


def test_parse_external_timing_markers():
    parsed = parse_external_timing(
        "\n".join(
            [
                "normal output",
                "[TIMING] source=powershell phase=wsl_call_start t_ms=100.0",
                "[TIMING] source=powershell phase=wsl_call_end t_ms=150.5",
                "[TIMING] source=container phase=source_ros_env_start t_ms=200",
                "[TIMING] source=container phase=source_ros_env_end t_ms=275",
            ]
        )
    )

    assert parsed["available"] is True
    assert parsed["marker_count"] == 4
    assert parsed["durations_ms"]["powershell.wsl_call_ms"] == 50.5
    assert parsed["durations_ms"]["container.source_ros_env_ms"] == 75.0


def test_policy_failure_still_writes_latency_breakdown(tmp_path, monkeypatch):
    repo_root = make_repo(tmp_path)
    config_path = repo_root / "unknown_probe.yaml"
    config_path.write_text(yaml.safe_dump(scenario_config(task_name="unknown_probe", operator="B"), sort_keys=False), encoding="utf-8")

    monkeypatch.setattr(runner, "collect_capabilities", lambda root: {"schema_version": "0.2", "can_run_check": True})
    monkeypatch.setattr(artifacts, "collect_git_info", lambda root: {"commit": None, "branch": None, "dirty": None})

    result = runner.run_episode(config_path, repo_root=repo_root)
    latency = json.loads((result.episode_dir / "latency_breakdown.json").read_text(encoding="utf-8"))
    metrics = json.loads((result.episode_dir / "metrics.json").read_text(encoding="utf-8"))

    assert result.ok is False
    assert latency["entry_type"] == "scenario"
    assert latency["preflight_ms"] is not None
    assert latency["executor_total_ms"] is None
    assert latency["main_command_ms"] is None
    assert metrics["latency_breakdown_path"] == "latency_breakdown.json"


def test_analyze_episode_latency_summarizes_episode(tmp_path):
    episode_dir = tmp_path / "outputs" / "episodes" / "20260702_test"
    episode_dir.mkdir(parents=True)
    (episode_dir / "metrics.json").write_text(
        json.dumps(
            {
                "schema_version": "0.2",
                "run_id": "20260702_test",
                "task_name": "read_only_interfaces",
                "entry_type": "check",
                "ok": False,
            }
        ),
        encoding="utf-8",
    )
    (episode_dir / "result.json").write_text(json.dumps({"status": "failed"}), encoding="utf-8")
    (episode_dir / "latency_breakdown.json").write_text(
        json.dumps(
            {
                "schema_version": "0.2",
                "total_duration_ms": 1000,
                "main_command_ms": 700,
                "executor_total_ms": 710,
                "capabilities_collect_ms": 200,
                "artifact_write_ms": 10,
                "safe_stop_command_ms": None,
            }
        ),
        encoding="utf-8",
    )
    (episode_dir / "external_timing.json").write_text(
        json.dumps(
            {
                "schema_version": "0.2",
                "available": True,
                "durations_ms": {
                    "python_check.rostopic_available_ms": 1.5,
                    "python_check.rostopic_list_ms": 2.5,
                    "python_check.cmd_vel_ms": 3.5,
                    "python_check.mobile_manipulator_mpc_control_ms": 4.5,
                },
            }
        ),
        encoding="utf-8",
    )

    row = analyze_episode_latency.summarize_episode(episode_dir)

    assert row["run_id"] == "20260702_test"
    assert row["task_name"] == "read_only_interfaces"
    assert row["total_duration_ms"] == 1000.0
    assert row["main_command_ms"] == 700.0
    assert row["capabilities_collect_ms"] == 200.0
    assert row["ros_check_ms"] == 12.0
    assert row["external_timing_available"] is True

    csv_path = tmp_path / "summary.csv"
    md_path = tmp_path / "summary.md"
    analyze_episode_latency.write_csv(csv_path, [row])
    analyze_episode_latency.write_markdown(md_path, [row], 1)

    assert "ros_check_ms" in csv_path.read_text(encoding="utf-8")
    assert "20260702_test" in md_path.read_text(encoding="utf-8")
