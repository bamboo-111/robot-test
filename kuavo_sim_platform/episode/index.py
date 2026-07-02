"""Global run index helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def append_run_index(outputs_dir: Path, entry: dict[str, Any]) -> None:
    outputs_dir.mkdir(parents=True, exist_ok=True)
    index_path = outputs_dir / "run_index.jsonl"
    with index_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True))
        handle.write("\n")
