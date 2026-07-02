import json
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
    safe_stop_command_args,
    scenario_command_args,
)
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
            stdout="scenario stdout",
            stderr="scenario failed",
            command="mock scenario command",
        ),
    )
    monkeypatch.setattr(
        runner,
        "run_safe_stop",
        lambda root: SafeStopResult(
            attempted=True,
            ok=True,
            exit_code=0,
            stdout="safe stdout",
            stderr="",
            command="mock safe stop command",
            duration_sec=0.12,
            failure_reason=None,
        ),
    )
    monkeypatch.setattr(
        artifacts,
        "collect_capabilities",
        lambda root: {"schema_version": "0.2", "can_run_check": True, "can_run_scenario": None},
    )
    monkeypatch.setattr(artifacts, "collect_git_info", lambda root: {"commit": None, "branch": None, "dirty": None})

    result = runner.run_episode(config_path, repo_root=repo_root)
    episode_dir = result.episode_dir

    assert result.ok is False
    assert (episode_dir / "scenario.yaml").read_text(encoding="utf-8").startswith("name: base_probe")
    assert (episode_dir / "safe_stop_stdout.log").read_text(encoding="utf-8") == "safe stdout"
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

    manifest = json.loads((episode_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["artifacts"]["scenario"] == "scenario.yaml"
    assert manifest["artifacts"]["safe_stop"] == "safe_stop.json"
    assert manifest["artifacts"]["safe_stop_stdout"] == "safe_stop_stdout.log"

    events = (episode_dir / "events.jsonl").read_text(encoding="utf-8")
    assert '"stage": "scenario_start"' in events
    assert '"stage": "scenario_end"' in events
    assert '"stage": "safe_stop_start"' in events
    assert '"stage": "safe_stop_end"' in events
