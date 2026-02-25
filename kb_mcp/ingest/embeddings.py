from __future__ import annotations

from collections import OrderedDict
import hashlib
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


class _LRUEmbeddingCache:
    def __init__(self, max_items: int) -> None:
        self._max_items = max(1, max_items)
        self._store: OrderedDict[str, list[float]] = OrderedDict()

    @staticmethod
    def _key(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()

    def get(self, text: str) -> list[float] | None:
        key = self._key(text)
        value = self._store.get(key)
        if value is None:
            return None
        self._store.move_to_end(key)
        return list(value)

    def set(self, text: str, vector: list[float]) -> None:
        key = self._key(text)
        self._store[key] = list(vector)
        self._store.move_to_end(key)
        while len(self._store) > self._max_items:
            self._store.popitem(last=False)


def _iter_batches(items: list[str], size: int) -> list[list[str]]:
    chunk_size = max(1, size)
    return [items[idx:idx + chunk_size] for idx in range(0, len(items), chunk_size)]


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
    def __init__(
        self,
        model_name: str,
        *,
        model_revision: str = "",
        batch_size: int = 32,
        cache_enabled: bool = True,
        cache_max_items: int = 4096,
        fallback: Embedder | None = None,
    ) -> None:
        self._fallback = fallback or DeterministicFallbackEmbedder()
        self._model = None
        self._dimensions = self._fallback.dimensions
        self._batch_size = max(1, batch_size)
        self._cache = _LRUEmbeddingCache(cache_max_items) if cache_enabled else None

        try:
            from sentence_transformers import SentenceTransformer

            revision = model_revision.strip()
            if revision:
                model = SentenceTransformer(model_name, revision=revision)
            else:
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

        out: list[list[float] | None] = [None] * len(texts)
        misses: list[str] = []
        miss_positions: dict[str, list[int]] = {}

        for idx, text in enumerate(texts):
            cached = self._cache.get(text) if self._cache is not None else None
            if cached is not None:
                out[idx] = cached
                continue
            bucket = miss_positions.setdefault(text, [])
            bucket.append(idx)
            if len(bucket) == 1:
                misses.append(text)

        if misses:
            try:
                encoded: list[list[float]] = []
                for batch in _iter_batches(misses, self._batch_size):
                    vectors = self._model.encode(
                        batch,
                        normalize_embeddings=True,
                        batch_size=self._batch_size,
                    )
                    encoded.extend([[float(v) for v in vec] for vec in vectors])
            except Exception:
                return self._fallback.embed_texts(texts)

            if len(encoded) != len(misses):
                return self._fallback.embed_texts(texts)

            for text, vector in zip(misses, encoded, strict=True):
                if self._cache is not None:
                    self._cache.set(text, vector)
                for idx in miss_positions.get(text, []):
                    out[idx] = list(vector)

        final = [item for item in out if item is not None]
        if len(final) != len(texts):
            return self._fallback.embed_texts(texts)
        return [[float(v) for v in item] for item in final]


class OpenAICompatibleEmbedder:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        dimensions: int,
        timeout_s: float = 10.0,
        batch_size: int = 32,
        cache_enabled: bool = True,
        cache_max_items: int = 4096,
        fallback: Embedder | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._dimensions = dimensions
        self._timeout_s = timeout_s
        self._batch_size = max(1, batch_size)
        self._cache = _LRUEmbeddingCache(cache_max_items) if cache_enabled else None
        self._fallback = fallback or DeterministicFallbackEmbedder(dimensions=dimensions)

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def _embed_remote_batch(self, texts: list[str]) -> list[list[float]] | None:
        with httpx.Client(timeout=self._timeout_s) as client:
            resp = client.post(
                f"{self._base_url}/embeddings",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"model": self._model, "input": texts},
            )
            resp.raise_for_status()
            payload = resp.json()

        data = payload.get("data", [])
        out: list[list[float]] = []
        for item in data:
            emb = item.get("embedding", [])
            if not isinstance(emb, list):
                return None
            vector = [float(v) for v in emb[:self._dimensions]]
            if len(vector) < self._dimensions:
                vector.extend([0.0] * (self._dimensions - len(vector)))
            out.append(vector)
        if len(out) != len(texts):
            return None
        return out

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not self._base_url or not self._api_key:
            return self._fallback.embed_texts(texts)

        out: list[list[float] | None] = [None] * len(texts)
        misses: list[str] = []
        miss_positions: dict[str, list[int]] = {}

        for idx, text in enumerate(texts):
            cached = self._cache.get(text) if self._cache is not None else None
            if cached is not None:
                out[idx] = cached
                continue
            bucket = miss_positions.setdefault(text, [])
            bucket.append(idx)
            if len(bucket) == 1:
                misses.append(text)

        if misses:
            for batch in _iter_batches(misses, self._batch_size):
                try:
                    vectors = self._embed_remote_batch(batch)
                except Exception:
                    vectors = None

                if vectors is None:
                    vectors = self._fallback.embed_texts(batch)

                for text, vector in zip(batch, vectors, strict=True):
                    if self._cache is not None:
                        self._cache.set(text, vector)
                    for idx in miss_positions.get(text, []):
                        out[idx] = list(vector)

        final = [item for item in out if item is not None]
        if len(final) != len(texts):
            return self._fallback.embed_texts(texts)
        return [[float(v) for v in item] for item in final]
