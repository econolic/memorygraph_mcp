from __future__ import annotations

import time
from collections import defaultdict
from contextlib import contextmanager
from collections.abc import Iterator


class MetricsRegistry:
    def __init__(self) -> None:
        self.counters: dict[str, int] = defaultdict(int)
        self.timers_ms: dict[str, list[float]] = defaultdict(list)

    def inc(self, key: str, n: int = 1) -> None:
        self.counters[key] += n

    @contextmanager
    def timer(self, key: str) -> Iterator[None]:
        start = time.perf_counter()
        try:
            yield
        finally:
            self.timers_ms[key].append((time.perf_counter() - start) * 1000)

    def snapshot(self) -> dict[str, object]:
        p95: dict[str, float] = {}
        for key, values in self.timers_ms.items():
            if not values:
                continue
            sorted_vals = sorted(values)
            idx = max(0, int(0.95 * (len(sorted_vals) - 1)))
            p95[key] = sorted_vals[idx]
        return {"counters": dict(self.counters), "p95_ms": p95}
