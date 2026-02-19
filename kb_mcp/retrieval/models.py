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
    score: float
    score_breakdown: dict[str, float]


@dataclass(frozen=True)
class RetrievalDebug:
    latency_ms: dict[str, int]
    fallback_mode: str | None = None
    fallback_reason: str | None = None
