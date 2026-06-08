from __future__ import annotations

import time
import math
from typing import Any

from kb_mcp.ingest.embeddings import (
    EMBEDDING_PRESETS,
    LocalSentenceTransformerEmbedder,
    OpenAICompatibleEmbedder,
)
from kb_mcp.ingest.chunking import chunk_text
from kb_mcp.retrieval.query_expand import QueryExpander
from kb_mcp.storage.metadata_store import MetadataStore
from kb_mcp.storage.sql_metadata_store import SQLMetadataStore
from kb_mcp.memory.service import MemoryService
from kb_mcp.memory.validator import ValidationResult
from kb_mcp.middleware.rate_limit import TokenBucket, RateLimiter
from kb_mcp.middleware.circuit_breaker import CircuitBreaker
from kb_mcp.security.confirmation import ConfirmationGate


# --- 1. Embedding Presets & Prefixing Tests ---

class MockSentenceTransformer:
    def __init__(self, *args, **kwargs) -> None:
        self.encode_calls = []

    def encode(self, texts, normalize_embeddings=True, batch_size=None):
        self.encode_calls.append(texts)
        return [[0.1] * 384 for _ in texts]


def test_embedding_presets() -> None:
    assert "multilingual-e5-large" in EMBEDDING_PRESETS
    preset = EMBEDDING_PRESETS["multilingual-e5-large"]
    assert preset["query_prefix"] == "query: "
    assert preset["passage_prefix"] == "passage: "


def test_local_embedder_prefixes(monkeypatch) -> None:
    import sys
    import types
    mock_instance = MockSentenceTransformer()
    fake_module = types.SimpleNamespace(SentenceTransformer=lambda *args, **kwargs: mock_instance)
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)

    embedder = LocalSentenceTransformerEmbedder(
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        query_prefix="query: ",
        passage_prefix="passage: ",
        cache_enabled=False,
    )
    # Force mock sentence transformer to be active
    embedder._model = mock_instance

    _ = embedder.embed_query("hello")
    _ = embedder.embed_texts(["world"])

    assert len(mock_instance.encode_calls) == 3
    assert mock_instance.encode_calls[0] == ["dimension_probe"]
    assert mock_instance.encode_calls[1] == ["query: hello"]
    assert mock_instance.encode_calls[2] == ["passage: world"]


def test_openai_embedder_prefixes(monkeypatch) -> None:
    recorded_jsons = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            pass
        def json(self) -> dict[str, Any]:
            return {"data": [{"embedding": [0.2] * 4}]}

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass
        def __enter__(self) -> FakeClient:
            return self
        def __exit__(self, exc_type, exc, tb) -> bool:
            return False
        def post(self, url: str, headers: dict, json: dict) -> FakeResponse:
            recorded_jsons.append(json)
            return FakeResponse()

    monkeypatch.setattr("kb_mcp.ingest.embeddings.httpx.Client", FakeClient)

    embedder = OpenAICompatibleEmbedder(
        base_url="http://mock-openai",
        api_key="key",
        model="text-embedding-3-small",
        dimensions=4,
        query_prefix="q_pref: ",
        passage_prefix="p_pref: ",
        cache_enabled=False,
    )

    _ = embedder.embed_query("hello")
    _ = embedder.embed_texts(["world"])

    assert len(recorded_jsons) == 2
    assert recorded_jsons[0]["input"] == ["q_pref: hello"]
    assert recorded_jsons[1]["input"] == ["p_pref: world"]


# --- 2. Chunking Modes Tests ---

class ConstantMockEmbedder:
    def __init__(self, scores: list[float]) -> None:
        self.scores = scores
        self.idx = 0
        self.dimensions = 2

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        # Return simple 2D unit vectors that yield specific similarity
        # Cosine similarity of [cos(a), sin(a)] and [cos(b), sin(b)] is cos(a-b)
        results = []
        for _ in texts:
            if self.idx < len(self.scores):
                angle = self.scores[self.idx]
                self.idx += 1
            else:
                angle = 0.0
            results.append([math.cos(angle), math.sin(angle)])
        return results

    def embed_query(self, text: str) -> list[float]:
        return [1.0, 0.0]


def test_semantic_chunking_similarity_grouping() -> None:
    # We want 3 sentences:
    # S1 & S2 are similar (angle difference is 0 -> sim 1.0)
    # S3 is different (angle difference is pi/2 -> sim 0.0)
    # Threshold = 0.5
    embedder = ConstantMockEmbedder([0.0, 0.0, math.pi / 2])
    text = "This is sentence one. This is sentence two. This is a very different topic."
    
    chunks = chunk_text(text, max_chars=50, overlap=10, mode="semantic", embedder=embedder, similarity_threshold=0.5)
    
    # S1 + S2 should group together. S3 should be separate.
    assert len(chunks) == 2
    assert "sentence one" in chunks[0]["text"]
    assert "sentence two" in chunks[0]["text"]
    assert "different topic" in chunks[1]["text"]


def test_code_chunking_python() -> None:
    code = (
        "import sys\n"
        "\n"
        "class MyClass:\n"
        "    def method(self):\n"
        "        pass\n"
        "\n"
        "def helper_func():\n"
        "    return 42\n"
    )
    # Python code chunking splits on 'class ' and 'def ' at col 0.
    chunks = chunk_text(code, max_chars=60, overlap=10, mode="code", language="python")
    assert len(chunks) == 3
    assert "import sys" in chunks[0]["text"]
    assert "class MyClass:" in chunks[1]["text"]
    assert "def helper_func():" in chunks[2]["text"]


# --- 3. Query Expansion Tests ---

class ExpansionMockEmbedder:
    def __init__(self) -> None:
        self.dimensions = 2

    def embed_query(self, text: str) -> list[float]:
        if "auth" in text:
            return [1.0, 0.0]
        return [0.0, 1.0]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            if "auth" in text.lower() or "login" in text.lower():
                out.append([0.99, 0.1])  # high similarity to [1.0, 0.0] (auth query)
            else:
                out.append([0.1, 0.99])  # low similarity to auth query
        return out


def test_query_expansion() -> None:
    meta = MetadataStore()
    meta.put_entity("kb://ent1", {"name": "AuthService", "workspace_id": "ws-1", "aliases": ["login_module"]})
    meta.put_entity("kb://ent2", {"name": "DatabaseConnector", "workspace_id": "ws-1"})

    embedder = ExpansionMockEmbedder()
    expander = QueryExpander(embedder=embedder, metadata=meta)

    expanded = expander.expand("how to use auth?", workspace_id="ws-1", max_expansions=2)
    
    # Should append "AuthService" and "login_module" but not DatabaseConnector
    assert "AuthService" in expanded
    assert "login_module" in expanded
    assert "DatabaseConnector" not in expanded


# --- 4. Idempotency Tests ---

class MockVectorStore:
    def __init__(self) -> None:
        self.upserted_memory = []
        self.deleted_memory = []

    def upsert_memory(self, memory_id: str, text: str, payload: dict) -> None:
        self.upserted_memory.append((memory_id, text, payload))

    def search_memory(self, query: str, top_k: int, filters: dict) -> list:
        return []


class MockGraphStore:
    def __init__(self) -> None:
        self.linked = []

    def upsert_memory_links(self, memory_uri: str, entity_uris: list[str], workspace_id: str) -> None:
        self.linked.append((memory_uri, entity_uris, workspace_id))


class AlwaysTrueValidator:
    def validate(self, memory_type: str, text: str, citations: list, confidence: float) -> ValidationResult:
        return ValidationResult(ok=True, reasons=[])


def test_memory_service_idempotency() -> None:
    meta = MetadataStore()
    vector = MockVectorStore()
    graph = MockGraphStore()
    validator = AlwaysTrueValidator()

    service = MemoryService(
        vector_store=vector,
        graph_store=graph,
        metadata=meta,
        validator=validator
    )

    items = [{"type": "fact", "text": "Capital of France is Paris", "confidence": 1.0}]
    
    # First invocation
    ids1, reports1 = service.upsert(
        workspace_id="w1",
        subject="u1",
        session_id="s1",
        items=items,
        idempotency_key="idem-key-123"
    )
    assert len(ids1) == 1
    assert len(vector.upserted_memory) == 1

    # Second invocation with same key
    ids2, reports2 = service.upsert(
        workspace_id="w1",
        subject="u1",
        session_id="s1",
        items=items,
        idempotency_key="idem-key-123"
    )
    assert ids1 == ids2
    assert reports1 == reports2
    # Vector store should NOT have been called again (still length 1)
    assert len(vector.upserted_memory) == 1


def test_sql_metadata_store_idempotency(tmp_path) -> None:
    db_file = tmp_path / "metadata.db"
    dsn = f"sqlite:///{db_file}"
    store = SQLMetadataStore(dsn=dsn)

    result_payload = {"stored_ids": ["id-1"], "validation_report": {}}
    store.set_idempotency("key-abc", result_payload)

    retrieved = store.get_idempotency("key-abc")
    assert retrieved == result_payload

    # Non-existent key
    assert store.get_idempotency("key-xyz") is None


# --- 5. Rate Limiting Tests ---

def test_token_bucket() -> None:
    # Rate = 10 rps, Burst = 2
    bucket = TokenBucket(rps=10.0, burst=2)
    
    # Initial state should allow burst consume
    assert bucket.consume() is True
    assert bucket.consume() is True
    # Bucket is empty now
    assert bucket.consume() is False


def test_rate_limiter() -> None:
    limiter = RateLimiter(rps=100.0, burst=1)
    assert limiter.is_allowed("user1", "ws1", "tool1") is True
    # Exceeded burst
    assert limiter.is_allowed("user1", "ws1", "tool1") is False
    # Scope isolated - other tool or user should be allowed
    assert limiter.is_allowed("user2", "ws1", "tool1") is True


# --- 6. Circuit Breaker Tests ---

def test_circuit_breaker() -> None:
    breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=0.1)
    
    # Starts CLOSED
    assert breaker.allow_request() is True

    # Failures count
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.allow_request() is True  # still closed (failures=2 < threshold=3)

    breaker.record_failure()
    assert breaker.state == "OPEN"
    assert breaker.allow_request() is False  # tripped

    # Recovery wait
    time.sleep(0.12)
    # Next request allowed under HALF_OPEN
    assert breaker.allow_request() is True
    assert breaker.state == "HALF_OPEN"

    # Success restores to CLOSED
    breaker.record_success()
    assert breaker.state == "CLOSED"
    assert breaker.failures == 0


# --- 7. Confirmation Gate Tests ---

def test_confirmation_gate() -> None:
    gate = ConfirmationGate(expiry_seconds=0.1)
    
    data = {"action": "delete", "uri": "kb://memory/1"}
    token = gate.generate_token(data)
    assert token.startswith("token_")

    # Correct validation fetches data and invalidates token
    validated = gate.validate_and_invalidate(token)
    assert validated == data

    # Double validation returns None (invalidated)
    assert gate.validate_and_invalidate(token) is None

    # Expiry validation
    token2 = gate.generate_token(data)
    time.sleep(0.15)
    assert gate.validate_and_invalidate(token2) is None
