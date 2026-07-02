"""Minimal v0.2 policy checks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class PolicyError(PermissionError):
    """Raised when a config is denied by policy."""


def load_policy(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise PolicyError(f"policy must be a mapping: {path}")
    return data


def check_policy(config: dict[str, Any], policy: dict[str, Any]) -> None:
    operator = str(config.get("operator", "")).strip()
    entry_type = str(config.get("entry_type", "")).strip()
    task_name = str(config.get("task_name", "")).strip()

    roles = policy.get("roles") or {}
    role = roles.get(operator)
    if not isinstance(role, dict):
        raise PolicyError(f"operator {operator!r} is not defined in policy")

    allowed_entry_types = role.get("allow_entry_types") or []
    if entry_type not in allowed_entry_types:
        raise PolicyError(f"operator {operator!r} may not run entry_type {entry_type!r}")

    if operator in {"B", "C"} and entry_type == "script":
        raise PolicyError("B/C operators may not run script entries in v0.2-alpha")

    allowed_tasks = role.get("allowed_tasks")
    if allowed_tasks != "*" and task_name not in set(allowed_tasks or []):
        raise PolicyError(f"operator {operator!r} may not run task {task_name!r}")

    if bool(config.get("safety", {}).get("allow_motion")) and not bool(role.get("allow_motion")):
        raise PolicyError(f"operator {operator!r} may not run motion tasks")

    if entry_type == "scenario":
        scenario_file = str(config.get("scenario", {}).get("file", "")).strip()
        scenario_whitelist = set(policy.get("scenario_whitelist") or [])
        if not scenario_whitelist:
            raise PolicyError("policy scenario_whitelist is empty")
        if scenario_file not in scenario_whitelist:
            raise PolicyError(f"scenario is not whitelisted: {scenario_file!r}")
