from __future__ import annotations

import hashlib


class LocalEmbeddingProvider:
    """Deterministic local fallback embedding provider."""

    def embed(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        vec = [float(b) / 255.0 for b in digest[:64]]
        return vec + [0.0] * (384 - len(vec))
