from __future__ import annotations

from kb_mcp.retrieval.router import QueryRouter


def test_router_keeps_requested_mode() -> None:
    routed = QueryRouter().route("simple query", "vector")
    assert routed.mode == "vector"
    assert routed.reason == "requested_mode"


def test_router_detects_structural_query() -> None:
    routed = QueryRouter().route("Какие зависимости у сервиса X", "hybrid")
    assert routed.mode == "hybrid"
    assert routed.reason == "structural_query"
