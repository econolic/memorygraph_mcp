from __future__ import annotations

from kb_mcp.observability.metrics import MetricsRegistry


def test_metrics_registry_tracks_counters_and_timers() -> None:
    metrics = MetricsRegistry(prometheus_enabled=False)
    metrics.inc("tool.kb.search.calls")
    metrics.observe("tool.kb.search.latency_ms", 12.0)
    metrics.observe("tool.kb.search.latency_ms", 18.0)
    metrics.observe("retrieval.stage.latency_ms", 5.0, labels={"stage": "graph"})

    snap = metrics.snapshot()
    counters = snap.get("counters", {})
    p95 = snap.get("p95_ms", {})

    assert isinstance(counters, dict)
    assert counters.get("tool.kb.search.calls") == 1
    assert isinstance(p95, dict)
    assert "tool.kb.search.latency_ms" in p95
    assert "retrieval.stage.latency_ms" in p95


def test_metrics_timer_context_observes_duration() -> None:
    metrics = MetricsRegistry(prometheus_enabled=False)
    with metrics.timer("tool.kb.graph_expand.latency_ms"):
        _ = sum(range(1000))
    snap = metrics.snapshot()
    p95 = snap.get("p95_ms", {})
    assert isinstance(p95, dict)
    assert "tool.kb.graph_expand.latency_ms" in p95
