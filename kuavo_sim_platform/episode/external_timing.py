"""Parse external timing markers emitted by scripts."""

from __future__ import annotations

import re
from typing import Any

from .schema import SCHEMA_VERSION


TIMING_PREFIX = "[TIMING]"
TOKEN_RE = re.compile(r"([A-Za-z0-9_.-]+)=([^ ]+)")


def parse_timing_line(line: str) -> dict[str, Any] | None:
    if TIMING_PREFIX not in line:
        return None
    payload = line.split(TIMING_PREFIX, 1)[1].strip()
    fields: dict[str, Any] = {}
    for key, value in TOKEN_RE.findall(payload):
        fields[key] = value
    if "phase" not in fields:
        return None
    if "t_ms" in fields:
        try:
            fields["t_ms"] = float(fields["t_ms"])
        except ValueError:
            fields["t_ms_parse_error"] = fields["t_ms"]
            fields["t_ms"] = None
    return fields


def parse_external_timing(*texts: str) -> dict[str, Any]:
    markers: list[dict[str, Any]] = []
    for stream, text in enumerate(texts):
        for line_no, line in enumerate((text or "").splitlines(), start=1):
            marker = parse_timing_line(line)
            if marker is None:
                continue
            marker["stream_index"] = stream
            marker["line_no"] = line_no
            markers.append(marker)

    return {
        "schema_version": SCHEMA_VERSION,
        "available": bool(markers),
        "marker_count": len(markers),
        "markers": markers,
        "durations_ms": compute_durations(markers),
        "notes": [] if markers else ["No external timing markers were found."],
    }


def compute_durations(markers: list[dict[str, Any]]) -> dict[str, float]:
    starts: dict[tuple[str, str], float] = {}
    durations: dict[str, float] = {}
    counts: dict[str, int] = {}
    for marker in markers:
        phase = str(marker.get("phase") or "")
        t_ms = marker.get("t_ms")
        if not phase or t_ms is None:
            continue
        source = str(marker.get("source") or "unknown")
        if phase.endswith("_start"):
            starts[(source, phase[:-6])] = float(t_ms)
        elif phase.endswith("_end"):
            base = phase[:-4]
            start = starts.get((source, base))
            if start is not None:
                key_base = f"{source}.{base}_ms"
                count = counts.get(key_base, 0) + 1
                counts[key_base] = count
                key = key_base if count == 1 else f"{key_base}#{count}"
                durations[key] = round(float(t_ms) - start, 3)
    return durations
