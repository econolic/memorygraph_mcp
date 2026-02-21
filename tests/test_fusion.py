from __future__ import annotations

from kb_mcp.retrieval.fusion import FusionWeights, fuse_scores, rrf_fuse


def test_fuse_scores_linear() -> None:
    score = fuse_scores(
        vector_score=0.8,
        graph_score=0.2,
        memory_score=0.4,
        weights=FusionWeights(w_vector=0.7, w_graph=0.2, w_memory=0.1),
    )
    assert abs(score - (0.8 * 0.7 + 0.2 * 0.2 + 0.4 * 0.1)) < 1e-9


def test_rrf_fuse_combines_ranked_lists() -> None:
    scores = rrf_fuse(
        ranked_uris_by_signal={
            "vector": ["kb://chunk/a", "kb://chunk/b"],
            "graph": ["kb://chunk/b"],
        },
        k=60,
    )
    assert scores["kb://chunk/b"] > scores["kb://chunk/a"]
