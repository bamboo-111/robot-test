"""Timing helpers for episode latency artifacts."""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator


class TimingCollector:
    """Collect named monotonic durations in milliseconds."""

    def __init__(self) -> None:
        self._starts: dict[str, float] = {}
        self._values_ms: dict[str, float | None] = {}

    def start(self, name: str) -> None:
        self._starts[name] = time.monotonic()

    def end(self, name: str) -> None:
        start = self._starts.pop(name, None)
        if start is None:
            self._values_ms[name] = None
            return
        self._values_ms[name] = round((time.monotonic() - start) * 1000, 3)

    @contextmanager
    def measure(self, name: str) -> Iterator[None]:
        self.start(name)
        try:
            yield
        finally:
            self.end(name)

    def set_ms(self, name: str, value: float | None) -> None:
        self._values_ms[name] = None if value is None else round(float(value), 3)

    def get_ms(self, name: str) -> float | None:
        return self._values_ms.get(name)

    def as_dict(self) -> dict[str, float | None]:
        return dict(self._values_ms)


def sec_to_ms(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value) * 1000, 3)
