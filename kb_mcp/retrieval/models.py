from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class VectorHit:
    item_id: str
    score: float
    payload: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphNode:
    uri: str
    type: str
    name: str
    properties: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphEdge:
    src: str
    rel: str
    dst: str


@dataclass(frozen=True)
class RetrievedItem:
    uri: str
    text: str
    score: float
    score_breakdown: dict[str, float]


@dataclass(frozen=True)
class RetrievalDebug:
    latency_ms: dict[str, int]
    fallback_mode: str | None = None
    fallback_reason: str | None = None
    fusion_mode: str = "linear"
    graph_seed_count: int = 0
    graph_node_count: int = 0
    graph_chunk_bonus_count: int = 0
    graph_nonzero: bool = False
