from __future__ import annotations

import math
from typing import Protocol

import httpx


class Embedder(Protocol):
    @property
    def dimensions(self) -> int:
        raise NotImplementedError

    def embed_query(self, text: str) -> list[float]:
        raise NotImplementedError

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


class DeterministicFallbackEmbedder:
    def __init__(self, dimensions: int = 384) -> None:
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _embed_one(self, text: str) -> list[float]:
        dense = [0.0] * self._dimensions
        raw = text.encode("utf-8", errors="ignore")
        if not raw:
            return dense

        for byte in raw:
            idx = byte if byte < self._dimensions else byte % self._dimensions
            dense[idx] += 1.0

        # Lightweight non-hash lexical features in the tail if dimensions allow it.
        if self._dimensions > 256:
            words = text.split()
            dense[256] = float(len(words))
        if self._dimensions > 257:
            dense[257] = float(len(text))
        if self._dimensions > 258:
            dense[258] = float(sum(ch.isdigit() for ch in text))
        if self._dimensions > 259:
            dense[259] = float(sum(ch.isupper() for ch in text))

        norm = math.sqrt(sum(v * v for v in dense))
        if norm <= 0.0:
            return dense
        return [v / norm for v in dense]

    def embed_query(self, text: str) -> list[float]:
        return self._embed_one(text)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]


class LocalSentenceTransformerEmbedder:
    def __init__(self, model_name: str, fallback: Embedder | None = None) -> None:
        self._fallback = fallback or DeterministicFallbackEmbedder()
        self._model = None
        self._dimensions = self._fallback.dimensions

        try:
            from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]

            model = SentenceTransformer(model_name)
            sample = model.encode(["dimension_probe"], normalize_embeddings=True)
            if len(sample) > 0:
                self._dimensions = len(sample[0])
            self._model = model
        except Exception:
            self._model = None

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if self._model is None:
            return self._fallback.embed_texts(texts)
        vectors = self._model.encode(texts, normalize_embeddings=True)
        return [[float(v) for v in vec] for vec in vectors]


class OpenAICompatibleEmbedder:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        dimensions: int,
        timeout_s: float = 10.0,
        fallback: Embedder | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._dimensions = dimensions
        self._timeout_s = timeout_s
        self._fallback = fallback or DeterministicFallbackEmbedder(dimensions=dimensions)

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not self._base_url or not self._api_key:
            return self._fallback.embed_texts(texts)
        try:
            with httpx.Client(timeout=self._timeout_s) as client:
                resp = client.post(
                    f"{self._base_url}/embeddings",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={"model": self._model, "input": texts},
                )
                resp.raise_for_status()
                payload = resp.json()
        except Exception:
            return self._fallback.embed_texts(texts)

        data = payload.get("data", [])
        out: list[list[float]] = []
        for item in data:
            emb = item.get("embedding", [])
            if not isinstance(emb, list):
                continue
            vector = [float(v) for v in emb[:self._dimensions]]
            if len(vector) < self._dimensions:
                vector.extend([0.0] * (self._dimensions - len(vector)))
            out.append(vector)
        if len(out) != len(texts):
            return self._fallback.embed_texts(texts)
        return out
