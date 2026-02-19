from __future__ import annotations

from dataclasses import dataclass

from kb_mcp.retrieval.models import RetrievedItem


@dataclass(frozen=True)
class RerankConfig:
    enabled: bool = True
    provider: str = "cross_encoder"
    top_n: int = 10


class CrossEncoderReranker:
    """Always-on reranker with lightweight fallback when model is unavailable."""

    def __init__(self) -> None:
        self._model = None
        try:
            from sentence_transformers import CrossEncoder  # type: ignore[import-not-found]

            self._model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
        except Exception:
            self._model = None

    def rerank(self, *, query: str, items: list[RetrievedItem], top_n: int) -> list[RetrievedItem]:
        if not items:
            return []

        if self._model is None:
            # Fallback lexical overlap scoring.
            q_tokens = set(query.lower().split())
            rescored: list[RetrievedItem] = []
            for item in items:
                uri_tokens = set(item.uri.lower().replace("/", " ").replace("_", " ").split())
                overlap = len(q_tokens & uri_tokens) / max(1, len(q_tokens))
                score = min(1.0, item.score + 0.1 * overlap)
                breakdown = dict(item.score_breakdown)
                breakdown["rerank"] = score
                rescored.append(RetrievedItem(uri=item.uri, score=score, score_breakdown=breakdown))
            rescored.sort(key=lambda x: x.score, reverse=True)
            return rescored[:top_n]

        pairs = [(query, item.uri) for item in items]
        scores = self._model.predict(pairs)
        rescored2: list[RetrievedItem] = []
        for item, score in zip(items, scores, strict=True):
            val = float(score)
            breakdown = dict(item.score_breakdown)
            breakdown["rerank"] = val
            rescored2.append(RetrievedItem(uri=item.uri, score=val, score_breakdown=breakdown))
        rescored2.sort(key=lambda x: x.score, reverse=True)
        return rescored2[:top_n]
