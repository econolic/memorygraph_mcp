from __future__ import annotations

import threading
import time
from collections import defaultdict
from contextlib import contextmanager
from collections.abc import Iterator
from typing import Any

try:
    from prometheus_client import CollectorRegistry, Counter, Histogram, start_http_server  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - optional dependency safety
    CollectorRegistry = None
    Counter = None
    Histogram = None
    start_http_server = None


_PROM_STARTED = False
_PROM_LOCK = threading.Lock()


class MetricsRegistry:
    def __init__(self, *, prometheus_enabled: bool = False) -> None:
        self.counters: dict[str, int] = defaultdict(int)
        self.timers_ms: dict[str, list[float]] = defaultdict(list)
        self._prometheus_enabled = bool(prometheus_enabled and CollectorRegistry and Counter and Histogram)
        self._prom_registry = CollectorRegistry() if self._prometheus_enabled else None

        self._tool_calls = None
        self._tool_latency = None
        self._retrieval_stage_latency = None
        self._auto_ingest_cycles = None
        self._auto_ingest_failures = None
        self._auto_ingest_retried_roots = None
        self._auto_ingest_root_failures = None

        if self._prometheus_enabled:
            self._tool_calls = Counter(
                "kb_tool_calls_total",
                "Total MCP tool calls",
                ["tool"],
                registry=self._prom_registry,
            )
            self._tool_latency = Histogram(
                "kb_tool_latency_seconds",
                "MCP tool latency in seconds",
                ["tool"],
                registry=self._prom_registry,
            )
            self._retrieval_stage_latency = Histogram(
                "kb_retrieval_stage_latency_seconds",
                "Hybrid retrieval stage latency in seconds",
                ["stage"],
                registry=self._prom_registry,
            )
            self._auto_ingest_cycles = Counter(
                "kb_auto_ingest_cycles_total",
                "Auto-ingest cycles by reason and status",
                ["reason", "status"],
                registry=self._prom_registry,
            )
            self._auto_ingest_failures = Counter(
                "kb_auto_ingest_failed_roots_total",
                "Auto-ingest failed roots count",
                registry=self._prom_registry,
            )
            self._auto_ingest_retried_roots = Counter(
                "kb_auto_ingest_retried_roots_total",
                "Auto-ingest roots that required retries",
                registry=self._prom_registry,
            )
            self._auto_ingest_root_failures = Counter(
                "kb_auto_ingest_root_failures_total",
                "Auto-ingest root failures by reason/method/error kind",
                ["reason", "method", "error_kind"],
                registry=self._prom_registry,
            )

    @property
    def prometheus_registry(self) -> object | None:
        return self._prom_registry

    @property
    def prometheus_enabled(self) -> bool:
        return self._prometheus_enabled

    def inc(self, key: str, n: int = 1, *, labels: dict[str, str] | None = None) -> None:
        self.counters[key] += n
        if not self._prometheus_enabled:
            return

        labels = labels or {}
        if key.startswith("tool.") and key.endswith(".calls") and self._tool_calls is not None:
            tool_name = key.removeprefix("tool.").removesuffix(".calls")
            self._tool_calls.labels(tool=tool_name).inc(n)
            return

        if key == "auto_ingest.cycle" and self._auto_ingest_cycles is not None:
            reason = labels.get("reason", "unknown")
            status = labels.get("status", "ok")
            self._auto_ingest_cycles.labels(reason=reason, status=status).inc(n)
            return

        if key == "auto_ingest.failed_roots" and self._auto_ingest_failures is not None:
            self._auto_ingest_failures.inc(n)
            return

        if key == "auto_ingest.retried_roots" and self._auto_ingest_retried_roots is not None:
            self._auto_ingest_retried_roots.inc(n)
            return

        if key == "auto_ingest.root_failure" and self._auto_ingest_root_failures is not None:
            reason = labels.get("reason", "unknown")
            method = labels.get("method", "unknown")
            error_kind = labels.get("error_kind", "unknown")
            self._auto_ingest_root_failures.labels(
                reason=reason,
                method=method,
                error_kind=error_kind,
            ).inc(n)

    def observe(self, key: str, value_ms: float, *, labels: dict[str, str] | None = None) -> None:
        self.timers_ms[key].append(float(value_ms))
        if not self._prometheus_enabled:
            return

        labels = labels or {}
        value_s = max(0.0, float(value_ms) / 1000.0)
        if key.startswith("tool.") and key.endswith(".latency_ms") and self._tool_latency is not None:
            tool_name = key.removeprefix("tool.").removesuffix(".latency_ms")
            self._tool_latency.labels(tool=tool_name).observe(value_s)
            return
        if key == "retrieval.stage.latency_ms" and self._retrieval_stage_latency is not None:
            stage = labels.get("stage", "unknown")
            self._retrieval_stage_latency.labels(stage=stage).observe(value_s)

    @contextmanager
    def timer(self, key: str, *, labels: dict[str, str] | None = None) -> Iterator[None]:
        start = time.perf_counter()
        try:
            yield
        finally:
            self.observe(key, (time.perf_counter() - start) * 1000.0, labels=labels)

    def snapshot(self) -> dict[str, object]:
        p95: dict[str, float] = {}
        for key, values in self.timers_ms.items():
            if not values:
                continue
            sorted_vals = sorted(values)
            idx = max(0, int(0.95 * (len(sorted_vals) - 1)))
            p95[key] = sorted_vals[idx]
        return {"counters": dict(self.counters), "p95_ms": p95}


def start_prometheus_exporter(*, port: int, registry: Any) -> bool:
    global _PROM_STARTED
    if start_http_server is None:
        return False
    with _PROM_LOCK:
        if _PROM_STARTED:
            return False
        start_http_server(port, registry=registry)
        _PROM_STARTED = True
        return True
