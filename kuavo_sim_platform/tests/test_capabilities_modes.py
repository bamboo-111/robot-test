"""Tests for the capabilities collection modes added in B-2."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from kuavo_sim_platform.episode import artifacts
from kuavo_sim_platform.episode.artifacts import (
    DEFAULT_CAPABILITIES_MAX_AGE_SEC,
    capabilities_cache_path,
    collect_capabilities,
    collect_full_capabilities,
    collect_minimal_capabilities,
)
from kuavo_sim_platform.episode.executors import ExecutorResult
from kuavo_sim_platform.episode import runner
from kuavo_sim_platform.episode.schema import ConfigError, resolve_config


def _make_repo(tmp_path: Path) -> Path:
    repo_root = tmp_path / "repo"
    (repo_root / "kuavo_sim_platform" / "scenarios").mkdir(parents=True)
    (repo_root / "configs" / "policies").mkdir(parents=True)
    (repo_root / "configs" / "policies" / "v0.2_policy.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": "0.2",
                "roles": {
                    "A": {"allow_entry_types": ["check"], "allowed_tasks": "*", "allow_motion": False},
                    "B": {"allow_entry_types": ["check"], "allowed_tasks": ["fast_health_check", "read_only_interfaces", "full_interfaces_check"], "allow_motion": False},
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return repo_root


def _check_config(**overrides):
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
    config.update(overrides)
    return config


# ---------------------------------------------------------------------------
# schema resolution
# ---------------------------------------------------------------------------
def test_resolve_config_defaults_capabilities_to_full(tmp_path):
    repo_root = _make_repo(tmp_path)
    resolved = resolve_config(_check_config(), repo_root)
    assert resolved["capabilities"] == {"mode": "full", "max_age_sec": 30}


def test_resolve_config_accepts_all_modes(tmp_path):
    repo_root = _make_repo(tmp_path)
    for mode in ("full", "cached", "minimal", "off"):
        resolved = resolve_config(
            _check_config(capabilities={"mode": mode, "max_age_sec": 5}),
            repo_root,
        )
        assert resolved["capabilities"] == {"mode": mode, "max_age_sec": 5}


def test_resolve_config_rejects_unknown_mode(tmp_path):
    repo_root = _make_repo(tmp_path)
    with pytest.raises(ConfigError, match="unsupported capabilities.mode"):
        resolve_config(_check_config(capabilities={"mode": "bogus"}), repo_root)


def test_resolve_config_rejects_nonpositive_max_age(tmp_path):
    repo_root = _make_repo(tmp_path)
    with pytest.raises(ConfigError, match="max_age_sec must be positive"):
        resolve_config(_check_config(capabilities={"mode": "cached", "max_age_sec": 0}), repo_root)


# ---------------------------------------------------------------------------
# collect_capabilities modes
# ---------------------------------------------------------------------------
def test_off_mode_returns_empty_and_no_capabilities_artifact(tmp_path, monkeypatch):
    repo_root = _make_repo(tmp_path)
    caps, meta = collect_capabilities(repo_root, mode="off")
    assert caps == {}
    assert meta == {"mode": "off", "cache_hit": False, "cache_age_sec": None}


def test_minimal_mode_skips_docker_probes(tmp_path, monkeypatch):
    repo_root = _make_repo(tmp_path)
    # If minimal accidentally called full collection, this docker probe would run.
    called = {"full": False}

    def fail_full(root):
        called["full"] = True
        return collect_full_capabilities(root)

    monkeypatch.setattr(artifacts, "collect_full_capabilities", fail_full)
    caps, meta = collect_capabilities(repo_root, mode="minimal")
    assert called["full"] is False
    assert meta == {"mode": "minimal", "cache_hit": False, "cache_age_sec": None}
    assert caps["web_backend_note"] == "minimal mode: not checked"
    assert caps["container_running"] is None


def test_cached_mode_writes_cache_on_miss_then_hits(tmp_path, monkeypatch):
    repo_root = _make_repo(tmp_path)
    monkeypatch.setattr(artifacts, "collect_git_info", lambda root: {"commit": None, "branch": None, "dirty": None})

    # First call: cache miss -> collects fresh, writes cache.
    caps1, meta1 = collect_capabilities(repo_root, mode="cached", max_age_sec=30)
    assert meta1["mode"] == "cached"
    assert meta1["cache_hit"] is False
    assert capabilities_cache_path(repo_root).is_file()

    # Second call immediately: cache hit.
    caps2, meta2 = collect_capabilities(repo_root, mode="cached", max_age_sec=30)
    assert meta2["cache_hit"] is True
    assert meta2["cache_age_sec"] is not None and meta2["cache_age_sec"] >= 0
    assert caps2["docker_cli_available"] == caps1["docker_cli_available"]


def test_cached_mode_treats_stale_cache_as_miss(tmp_path, monkeypatch):
    repo_root = _make_repo(tmp_path)
    monkeypatch.setattr(artifacts, "collect_git_info", lambda root: {"commit": None, "branch": None, "dirty": None})

    collect_capabilities(repo_root, mode="cached", max_age_sec=30)
    # A zero max_age forces every read to be a miss.
    _, meta = collect_capabilities(repo_root, mode="cached", max_age_sec=0)
    assert meta["cache_hit"] is False


# ---------------------------------------------------------------------------
# end-to-end: latency_breakdown records mode/cache_hit
# ---------------------------------------------------------------------------
def _write_check_config(repo_root: Path, capabilities: dict) -> Path:
    config_path = repo_root / "fast_health_check.yaml"
    config = _check_config(
        task_name="fast_health_check",
        check={"name": "fast_health"},
        capabilities=capabilities,
    )
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return config_path


def test_episode_records_capabilities_mode_in_latency_and_metrics(tmp_path, monkeypatch):
    repo_root = _make_repo(tmp_path)
    config_path = _write_check_config(repo_root, {"mode": "minimal", "max_age_sec": 30})

    monkeypatch.setattr(
        runner,
        "run_executor",
        lambda config, root: ExecutorResult(
            exit_code=0, ok=True, stdout="ok", stderr="", command="mock", duration_sec=0.1
        ),
    )
    monkeypatch.setattr(artifacts, "collect_git_info", lambda root: {"commit": None, "branch": None, "dirty": None})

    result = runner.run_episode(config_path, repo_root=repo_root)
    latency = json.loads((result.episode_dir / "latency_breakdown.json").read_text(encoding="utf-8"))
    metrics = json.loads((result.episode_dir / "metrics.json").read_text(encoding="utf-8"))

    assert latency["capabilities_mode"] == "minimal"
    assert latency["capabilities_cache_hit"] is False
    assert metrics["capabilities_mode"] == "minimal"
    assert metrics["capabilities_cache_hit"] is False


def test_episode_off_mode_omits_capabilities_json(tmp_path, monkeypatch):
    repo_root = _make_repo(tmp_path)
    config_path = _write_check_config(repo_root, {"mode": "off", "max_age_sec": 30})

    monkeypatch.setattr(
        runner,
        "run_executor",
        lambda config, root: ExecutorResult(
            exit_code=0, ok=True, stdout="ok", stderr="", command="mock", duration_sec=0.1
        ),
    )
    monkeypatch.setattr(artifacts, "collect_git_info", lambda root: {"commit": None, "branch": None, "dirty": None})

    result = runner.run_episode(config_path, repo_root=repo_root)
    # No capabilities.json should be written in off mode.
    assert not (result.episode_dir / "capabilities.json").exists()
    latency = json.loads((result.episode_dir / "latency_breakdown.json").read_text(encoding="utf-8"))
    assert latency["capabilities_mode"] == "off"
    assert latency["capabilities_collect_ms"] is not None
