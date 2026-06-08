from __future__ import annotations

import math
from dataclasses import dataclass
from threading import BoundedSemaphore

from kb_mcp.retrieval.models import RetrievedItem


@dataclass(frozen=True)
class RerankConfig:
    enabled: bool = True
    provider: str = "cross_encoder"
    top_n: int = 10


class CrossEncoderReranker:
    """Always-on reranker with lightweight fallback when model is unavailable."""

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2") -> None:
        self._model = None
        self._model_name = model_name
        self._initialized = False
        self._semaphore = BoundedSemaphore(value=1)

    def _ensure_model(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        import os
        if "PYTEST_CURRENT_TEST" in os.environ:
            return
        try:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self._model_name)
        except Exception:
            self._model = None

    @staticmethod
    def _sigmoid(value: float) -> float:
        if value >= 0:
            exp_neg = math.exp(-value)
            return 1.0 / (1.0 + exp_neg)
        exp_pos = math.exp(value)
        return exp_pos / (1.0 + exp_pos)

    def _normalize_score(self, raw_score: float) -> float:
        if 0.0 <= raw_score <= 1.0:
            return raw_score
        return self._sigmoid(raw_score)

    def rerank(self, *, query: str, items: list[RetrievedItem], top_n: int) -> list[RetrievedItem]:
        if not items:
            return []

        self._ensure_model()
        if self._model is None:
            q_tokens = set(query.lower().split())
            rescored: list[RetrievedItem] = []
            for item in items:
                text_tokens = set(item.text.lower().split())
                overlap = len(q_tokens & text_tokens) / max(1, len(q_tokens))
                rerank_score = overlap
                score = 0.7 * item.score + 0.3 * rerank_score
                breakdown = dict(item.score_breakdown)
                breakdown["rerank"] = rerank_score
                rescored.append(
                    RetrievedItem(
                        uri=item.uri,
                        text=item.text,
                        score=score,
                        score_breakdown=breakdown,
                    )
                )
            rescored.sort(key=lambda x: x.score, reverse=True)
            return rescored[:top_n]

        pairs = [(query, item.text or item.uri) for item in items]
        with self._semaphore:
            raw_scores = self._model.predict(pairs)
        rescored2: list[RetrievedItem] = []
        for item, raw_score in zip(items, raw_scores, strict=True):
            rerank_score = self._normalize_score(float(raw_score))
            score = 0.7 * item.score + 0.3 * rerank_score
            breakdown = dict(item.score_breakdown)
            breakdown["rerank"] = rerank_score
            rescored2.append(
                RetrievedItem(
                    uri=item.uri,
                    text=item.text,
                    score=score,
                    score_breakdown=breakdown,
                )
            )
        rescored2.sort(key=lambda x: x.score, reverse=True)
        return rescored2[:top_n]
