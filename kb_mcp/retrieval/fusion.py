from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FusionWeights:
    w_vector: float = 0.70
    w_graph: float = 0.20
    w_memory: float = 0.10


def fuse_scores(
    *,
    vector_score: float,
    graph_score: float,
    memory_score: float,
    weights: FusionWeights,
) -> float:
    return (
        weights.w_vector * vector_score
        + weights.w_graph * graph_score
        + weights.w_memory * memory_score
    )
