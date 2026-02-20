from __future__ import annotations

import time

from kb_mcp.retrieval.fusion import FusionWeights, fuse_scores
from kb_mcp.retrieval.graph_store import GraphStore
from kb_mcp.retrieval.models import RetrievedItem, RetrievalDebug
from kb_mcp.retrieval.rerank import CrossEncoderReranker, RerankConfig
from kb_mcp.retrieval.vector_store import VectorStore


class HybridRetriever:
    def __init__(
        self,
        *,
        vector_store: VectorStore,
        graph_store: GraphStore,
        reranker: CrossEncoderReranker,
        weights: FusionWeights | None = None,
    ) -> None:
        self._vector = vector_store
        self._graph = graph_store
        self._reranker = reranker
        self._weights = weights or FusionWeights()

    @staticmethod
    def _lexical_score(query: str, text: str) -> float:
        q_tokens = {token for token in query.lower().split() if token}
        if not q_tokens:
            return 0.0
        text_tokens = {token for token in text.lower().split() if token}
        return float(len(q_tokens & text_tokens)) / float(len(q_tokens))

    def search(
        self,
        *,
        query: str,
        top_k: int,
        filters: dict[str, object],
        depth: int,
        edge_types: list[str],
        max_nodes: int,
        memory_bonus_by_uri: dict[str, float] | None = None,
        rerank: RerankConfig | None = None,
    ) -> tuple[list[RetrievedItem], RetrievalDebug]:
        t0 = time.perf_counter()
        vector_hits = self._vector.search_chunks(query=query, top_k=top_k, filters=filters)
        t1 = time.perf_counter()

        fallback_mode: str | None = None
        fallback_reason: str | None = None

        try:
            seed_entities = self._graph.resolve_entities(query=query, filters=filters)
            nodes, _edges = self._graph.expand(
                seed_uris=seed_entities,
                depth=depth,
                edge_types=edge_types,
                max_nodes=max_nodes,
                filters=filters,
            )
            graph_bonus_by_uri = {n.uri: 1.0 for n in nodes}
        except Exception as exc:  # pragma: no cover - failure path integration-level
            fallback_mode = "vector"
            fallback_reason = str(exc)
            graph_bonus_by_uri = {}

        t2 = time.perf_counter()

        memory_bonus_by_uri = memory_bonus_by_uri or {}
        fused: list[RetrievedItem] = []
        for hit in vector_hits:
            uri = f"kb://chunk/{hit.item_id}"
            graph_score = graph_bonus_by_uri.get(uri, 0.0)
            memory_score = float(memory_bonus_by_uri.get(uri, 0.0))
            lexical_score = self._lexical_score(query, str(hit.payload.get("text", "")))
            base_total = fuse_scores(
                vector_score=hit.score,
                graph_score=graph_score,
                memory_score=memory_score,
                weights=self._weights,
            )
            # Keep baseline robust when rerank is disabled by blending lexical evidence.
            total = 0.6 * base_total + 0.4 * lexical_score
            fused.append(
                RetrievedItem(
                    uri=uri,
                    text=str(hit.payload.get("text", "")),
                    score=total,
                    score_breakdown={
                        "vector": hit.score,
                        "graph": graph_score,
                        "memory": memory_score,
                        "lexical": lexical_score,
                    },
                )
            )

        fused.sort(key=lambda item: item.score, reverse=True)
        t3 = time.perf_counter()

        cfg = rerank or RerankConfig(enabled=True, provider="cross_encoder", top_n=min(top_k, 10))
        reranked = fused
        if cfg.enabled:
            reranked = self._reranker.rerank(query=query, items=fused, top_n=min(cfg.top_n, top_k))

        t4 = time.perf_counter()
        debug = RetrievalDebug(
            latency_ms={
                "vector": int((t1 - t0) * 1000),
                "graph": int((t2 - t1) * 1000),
                "fusion": int((t3 - t2) * 1000),
                "rerank": int((t4 - t3) * 1000),
            },
            fallback_mode=fallback_mode,
            fallback_reason=fallback_reason,
        )
        return reranked[:top_k], debug
