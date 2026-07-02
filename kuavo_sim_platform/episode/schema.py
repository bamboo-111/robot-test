"""Config loading and validation for v0.2 episode runs."""

from __future__ import annotations

import copy
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import yaml


SCHEMA_VERSION = "0.2"
SUPPORTED_ENTRY_TYPES = {"check", "scenario"}
SUPPORTED_CHECKS = {"interfaces", "smoke_test"}
SCENARIO_WHITELIST = {"kuavo_sim_platform/scenarios/base_probe.yaml"}

DEFAULT_ARTIFACTS = {
    "save_stdout": True,
    "save_stderr": True,
    "save_config": True,
    "save_resolved_config": True,
    "save_manifest": True,
    "save_events": True,
    "save_capabilities": True,
    "save_scenario_copy": False,
    "save_safe_stop": False,
}

DEFAULT_SAFETY = {
    "require_preflight": False,
    "safe_stop_on_exit": False,
    "allow_motion": False,
}

DEFAULT_SUCCESS_CRITERIA = {
    "type": "exit_code_zero",
}


class ConfigError(ValueError):
    """Raised when an episode config is invalid."""


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"config must be a mapping: {path}")
    return data


def dump_yaml(path: Path, data: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        yaml.safe_dump(data, handle, sort_keys=False, allow_unicode=True)


def sanitize_task_name(value: str) -> str:
    cleaned = re.sub(r"\s+", "_", value.strip())
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", cleaned)
    cleaned = cleaned.strip("._-")
    return cleaned or "episode"


def normalize_repo_relative_path(value: str, repo_root: Path) -> tuple[str, Path]:
    raw_value = str(value or "").strip()
    if not raw_value:
        raise ConfigError("scenario.file is required")

    normalized = raw_value.replace("\\", "/")
    windows_path = PureWindowsPath(raw_value)
    posix_path = PurePosixPath(normalized)
    if windows_path.is_absolute() or windows_path.drive or windows_path.root or posix_path.is_absolute():
        raise ConfigError("scenario.file must be a repo-relative path")

    parts = posix_path.parts
    if any(part in {"..", ""} for part in parts):
        raise ConfigError("scenario.file may not escape the repository")

    relative_path = "/".join(parts)
    abs_path = (repo_root / Path(*parts)).resolve()
    resolved_repo_root = repo_root.resolve()
    try:
        abs_path.relative_to(resolved_repo_root)
    except ValueError as exc:
        raise ConfigError("scenario.file may not escape the repository") from exc

    return relative_path, abs_path


def resolve_scenario(config: dict[str, Any], repo_root: Path, whitelist: set[str] | None = None) -> dict[str, Any]:
    scenario = config.get("scenario") or {}
    if not isinstance(scenario, dict):
        raise ConfigError("scenario must be a mapping")

    scenario_file, abs_file = normalize_repo_relative_path(str(scenario.get("file", "")), repo_root)
    if abs_file.suffix.lower() not in {".yaml", ".yml"}:
        raise ConfigError("scenario.file must end with .yaml or .yml")
    if not abs_file.exists() or not abs_file.is_file():
        raise ConfigError(f"scenario.file does not exist: {scenario_file}")

    allowed = whitelist if whitelist is not None else SCENARIO_WHITELIST
    if scenario_file not in allowed:
        raise ConfigError(f"scenario.file is not whitelisted: {scenario_file}")

    container_root = str(scenario.get("container_root") or "/root/kuavo_deploy").strip()
    if not container_root:
        raise ConfigError("scenario.container_root is required")

    ready_timeout_sec = int(scenario.get("ready_timeout_sec", 30))
    if ready_timeout_sec <= 0:
        raise ConfigError("scenario.ready_timeout_sec must be positive")

    return {
        "file": scenario_file,
        "abs_file": str(abs_file),
        "container_root": container_root,
        "container_file": f"{container_root.rstrip('/')}/{scenario_file}",
        "ready_timeout_sec": ready_timeout_sec,
    }


def resolve_config(raw_config: dict[str, Any], repo_root: Path, operator_override: str | None = None) -> dict[str, Any]:
    config = copy.deepcopy(raw_config)

    schema_version = str(config.get("schema_version", "")).strip()
    if schema_version != SCHEMA_VERSION:
        raise ConfigError(f"schema_version must be {SCHEMA_VERSION!r}")

    task_name = str(config.get("task_name", "")).strip()
    if not task_name:
        raise ConfigError("task_name is required")

    entry_type = str(config.get("entry_type", "")).strip()
    if entry_type not in SUPPORTED_ENTRY_TYPES:
        raise ConfigError(f"entry_type {entry_type!r} is not supported in v0.2")

    operator = operator_override if operator_override is not None else config.get("operator")
    operator = str(operator or "").strip()
    if not operator:
        raise ConfigError("operator is required")

    permission_level = str(config.get("permission_level", "read_only")).strip() or "read_only"
    timeout_sec = int(config.get("timeout_sec", 30))
    if timeout_sec <= 0:
        raise ConfigError("timeout_sec must be positive")

    artifacts = dict(DEFAULT_ARTIFACTS)
    artifacts.update(config.get("artifacts") or {})

    safety = dict(DEFAULT_SAFETY)
    safety.update(config.get("safety") or {})

    if bool(safety.get("allow_motion")) and not bool(safety.get("safe_stop_on_exit")):
        raise ConfigError("motion tasks require safety.safe_stop_on_exit=true")

    success_criteria = dict(DEFAULT_SUCCESS_CRITERIA)
    success_criteria.update(config.get("success_criteria") or {})
    if success_criteria.get("type") != "exit_code_zero":
        raise ConfigError("only success_criteria.type=exit_code_zero is supported")

    check = config.get("check") or {}
    scenario: dict[str, Any] = {}
    if entry_type == "check":
        if not isinstance(check, dict):
            raise ConfigError("check must be a mapping")
        check_name = str(check.get("name", "")).strip()
        if check_name not in SUPPORTED_CHECKS:
            raise ConfigError(f"unsupported check.name: {check_name!r}")
        check = {"name": check_name}
    elif entry_type == "scenario":
        scenario = resolve_scenario(config, repo_root)
        check = {}

    resolved = {
        "schema_version": SCHEMA_VERSION,
        "repo_root": str(repo_root),
        "task_name": sanitize_task_name(task_name),
        "entry_type": entry_type,
        "operator": operator,
        "permission_level": permission_level,
        "timeout_sec": timeout_sec,
        "artifacts": artifacts,
        "safety": safety,
        "check": check,
        "scenario": scenario,
        "success_criteria": success_criteria,
    }

    return resolved
