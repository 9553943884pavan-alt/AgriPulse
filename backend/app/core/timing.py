"""Per-stage timing utility.

Usage:
    timer = StageTimer()
    with timer.stage("geocoding"):
        result = await locate(...)
    with timer.stage("weather"):
        wx = await get_weather(...)
    response.headers["Server-Timing"] = timer.server_timing_header()
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass


@dataclass
class _Stage:
    name: str
    start: float
    end: float = 0.0

    @property
    def duration_ms(self) -> float:
        return (self.end - self.start) * 1000


class StageTimer:
    def __init__(self) -> None:
        self._stages: list[_Stage] = []

    @contextmanager
    def stage(self, name: str):
        s = _Stage(name=name, start=time.perf_counter())
        try:
            yield s
        finally:
            s.end = time.perf_counter()
            self._stages.append(s)

    def server_timing_header(self) -> str:
        """Build a Server-Timing header value from all recorded stages."""
        parts = [f"{s.name};dur={s.duration_ms:.1f}" for s in self._stages]
        total = sum(s.duration_ms for s in self._stages)
        parts.append(f"total;dur={total:.1f}")
        return ", ".join(parts)

    def as_dict(self) -> dict[str, float]:
        return {s.name: round(s.duration_ms, 1) for s in self._stages}
