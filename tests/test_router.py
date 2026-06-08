from __future__ import annotations

from kb_mcp.retrieval.router import QueryRouter


def test_router_keeps_requested_mode() -> None:
    routed = QueryRouter().route("simple query", "vector")
    assert routed.mode == "vector"
    assert routed.reason == "requested_mode"
    assert routed.intent == "fact_lookup"
    assert routed.recommended_tools == ("kb_search",)


def test_router_detects_structural_query() -> None:
    routed = QueryRouter().route("Какие зависимости у сервиса X", "hybrid")
    assert routed.mode == "hybrid"
    assert routed.reason == "structural_query"
    assert routed.intent == "relation_impact"
    assert routed.recommended_tools == ("kb_search", "kb_graph_expand")


def test_router_detects_memory_intent_with_include_memory() -> None:
    routed = QueryRouter().route("simple query", "hybrid", include_memory=True)
    assert routed.intent == "memory_context"
    assert routed.recommended_tools == ("kb_memory_search", "kb_search")


def test_router_detects_memory_delete_intent() -> None:
    routed = QueryRouter().route("please delete memory about me", "hybrid")
    assert routed.intent == "memory_delete"
    assert routed.recommended_tools == ("kb_memory_delete",)
