from __future__ import annotations

import sys
import types

import httpx

from kb_mcp.ingest.embeddings import (
    DeterministicFallbackEmbedder,
    LocalSentenceTransformerEmbedder,
    OpenAICompatibleEmbedder,
)


def test_local_embedder_uses_batch_size_cache_and_revision(monkeypatch) -> None:
    class FakeSentenceTransformer:
        init_kwargs: list[dict[str, object]] = []
        encode_calls: list[dict[str, object]] = []

        def __init__(self, model_name: str, **kwargs) -> None:
            self.model_name = model_name
            self.kwargs = kwargs
            self.__class__.init_kwargs.append({"model_name": model_name, **kwargs})

        def encode(self, texts, normalize_embeddings=True, batch_size=None):  # noqa: ANN001
            self.__class__.encode_calls.append(
                {
                    "texts": list(texts),
                    "normalize_embeddings": normalize_embeddings,
                    "batch_size": batch_size,
                }
            )
            return [[float(len(text)), 1.0] for text in texts]

    fake_module = types.SimpleNamespace(SentenceTransformer=FakeSentenceTransformer)
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)

    embedder = LocalSentenceTransformerEmbedder(
        model_name="fake/model",
        model_revision="rev-123",
        batch_size=2,
        cache_enabled=True,
        cache_max_items=10,
        fallback=DeterministicFallbackEmbedder(dimensions=2),
    )

    first = embedder.embed_texts(["a", "bb", "a"])
    second = embedder.embed_texts(["a", "bb", "a"])

    assert first == second
    assert len(FakeSentenceTransformer.init_kwargs) == 1
    assert FakeSentenceTransformer.init_kwargs[0].get("revision") == "rev-123"
    # one probe + one batch call, no extra encode calls on cached second pass
    assert len(FakeSentenceTransformer.encode_calls) == 2
    assert any(call["batch_size"] == 2 for call in FakeSentenceTransformer.encode_calls)


def test_openai_embedder_batch_fallback_is_partial(monkeypatch) -> None:
    class FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return self._payload

    class FakeClient:
        def __init__(self, timeout: float) -> None:
            _ = timeout

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:  # noqa: ANN001
            _ = exc_type
            _ = exc
            _ = tb
            return False

        def post(self, url: str, headers: dict[str, str], json: dict[str, object]) -> FakeResponse:  # noqa: A002
            _ = url
            _ = headers
            inputs = json.get("input", [])
            if isinstance(inputs, list) and "fail1" in inputs:
                raise httpx.HTTPError("synthetic batch failure")
            if not isinstance(inputs, list):
                inputs = []
            payload = {"data": [{"embedding": [42.0, 42.0, 42.0, 42.0]} for _ in inputs]}
            return FakeResponse(payload)

    monkeypatch.setattr("kb_mcp.ingest.embeddings.httpx.Client", FakeClient)

    embedder = OpenAICompatibleEmbedder(
        base_url="http://fake-embeddings",
        api_key="secret",
        model="embedding-model",
        dimensions=4,
        batch_size=2,
        cache_enabled=True,
        cache_max_items=32,
        fallback=DeterministicFallbackEmbedder(dimensions=4),
    )

    vectors = embedder.embed_texts(["ok1", "fail1", "ok2", "ok1"])
    assert len(vectors) == 4
    assert vectors[2] == [42.0, 42.0, 42.0, 42.0]
    assert vectors[0] == vectors[3]
    assert vectors[0] != [42.0, 42.0, 42.0, 42.0]
