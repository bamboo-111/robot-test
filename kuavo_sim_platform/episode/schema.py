"""Config loading and validation for v0.2 episode runs."""

from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

import yaml


SCHEMA_VERSION = "0.2"
SUPPORTED_ENTRY_TYPES = {"check"}
SUPPORTED_CHECKS = {"interfaces", "smoke_test"}

DEFAULT_ARTIFACTS = {
    "save_stdout": True,
    "save_stderr": True,
    "save_config": True,
    "save_resolved_config": True,
    "save_manifest": True,
    "save_events": True,
    "save_capabilities": True,
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
        raise ConfigError(f"entry_type {entry_type!r} is not supported in v0.2-alpha")

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

    if bool(safety.get("allow_motion")):
        raise ConfigError("v0.2-alpha runner only supports non-motion checks")

    success_criteria = dict(DEFAULT_SUCCESS_CRITERIA)
    success_criteria.update(config.get("success_criteria") or {})
    if success_criteria.get("type") != "exit_code_zero":
        raise ConfigError("only success_criteria.type=exit_code_zero is supported")

    check = config.get("check") or {}
    if entry_type == "check":
        if not isinstance(check, dict):
            raise ConfigError("check must be a mapping")
        check_name = str(check.get("name", "")).strip()
        if check_name not in SUPPORTED_CHECKS:
            raise ConfigError(f"unsupported check.name: {check_name!r}")
        check = {"name": check_name}

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
        "success_criteria": success_criteria,
    }

    return resolved
