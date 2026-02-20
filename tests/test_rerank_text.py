from __future__ import annotations

from kb_mcp.retrieval.models import RetrievedItem
from kb_mcp.retrieval.rerank import CrossEncoderReranker


def test_rerank_fallback_uses_chunk_text_not_uri() -> None:
    reranker = CrossEncoderReranker()
    reranker._model = None

    items = [
        RetrievedItem(
            uri="kb://chunk/a",
            text="unrelated content",
            score=0.6,
            score_breakdown={"vector": 0.6, "graph": 0.0, "memory": 0.0},
        ),
        RetrievedItem(
            uri="kb://chunk/b",
            text="lagerid mapping and reconciliation details",
            score=0.4,
            score_breakdown={"vector": 0.4, "graph": 0.0, "memory": 0.0},
        ),
    ]

    ranked = reranker.rerank(query="lagerid mapping", items=items, top_n=2)
    assert ranked
    assert ranked[0].uri == "kb://chunk/b"
