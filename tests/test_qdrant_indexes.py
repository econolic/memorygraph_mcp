from __future__ import annotations

from types import SimpleNamespace

from qdrant_client.http import models

from kb_mcp.ingest.embeddings import DeterministicFallbackEmbedder
from kb_mcp.storage.qdrant_store import QdrantVectorStore


class _FakeQdrantClient:
    instances: list["_FakeQdrantClient"] = []
    global_created_indexes: set[tuple[str, str]] = set()

    def __init__(self, *, url: str) -> None:
        self.url = url
        self.created_indexes: set[tuple[str, str]] = set()
        self.create_payload_index_calls: list[tuple[str, str]] = []
        self.last_query_filter: models.Filter | None = None
        self.last_upsert_points: list[models.PointStruct] = []
        self.last_upsert_collection = ""
        _FakeQdrantClient.instances.append(self)

    def get_collection(self, *, collection_name: str) -> object:
        _ = collection_name
        vector_params = models.VectorParams(size=384, distance=models.Distance.COSINE)
        return SimpleNamespace(config=SimpleNamespace(params=SimpleNamespace(vectors=vector_params)))

    def create_collection(self, *, collection_name: str, vectors_config: models.VectorParams) -> None:
        _ = collection_name
        _ = vectors_config

    def create_payload_index(
        self,
        *,
        collection_name: str,
        field_name: str,
        field_schema: models.PayloadSchemaType,
        wait: bool = True,
    ) -> None:
        _ = field_schema
        _ = wait
        key = (collection_name, field_name)
        self.create_payload_index_calls.append(key)
        if key in self.global_created_indexes:
            raise RuntimeError("index already exists")
        self.created_indexes.add(key)
        self.global_created_indexes.add(key)

    def query_points(
        self,
        *,
        collection_name: str,
        query: list[float],
        query_filter: models.Filter | None,
        limit: int,
        with_payload: bool,
        with_vectors: bool,
    ) -> object:
        _ = collection_name
        _ = query
        _ = limit
        _ = with_payload
        _ = with_vectors
        self.last_query_filter = query_filter
        return SimpleNamespace(points=[])

    def upsert(
        self,
        *,
        collection_name: str,
        points: list[models.PointStruct],
        wait: bool = True,
    ) -> None:
        _ = collection_name
        _ = wait
        self.last_upsert_collection = collection_name
        self.last_upsert_points = points

    def delete(self, *, collection_name: str, points_selector: models.FilterSelector) -> None:
        _ = collection_name
        _ = points_selector


def test_qdrant_creates_payload_indexes_idempotently(monkeypatch) -> None:
    monkeypatch.setattr("kb_mcp.storage.qdrant_store.QdrantClient", _FakeQdrantClient)
    _FakeQdrantClient.instances.clear()
    _FakeQdrantClient.global_created_indexes.clear()

    QdrantVectorStore(
        url="http://fake-qdrant:6333",
        chunks_collection="kb_chunks",
        memory_collection="kb_memory",
        embedder=DeterministicFallbackEmbedder(dimensions=384),
    )
    QdrantVectorStore(
        url="http://fake-qdrant:6333",
        chunks_collection="kb_chunks",
        memory_collection="kb_memory",
        embedder=DeterministicFallbackEmbedder(dimensions=384),
    )

    assert len(_FakeQdrantClient.instances) == 2
    expected_fields = {"workspace_id", "acl_allow", "source", "source_path", "updated_at", "tags"}
    for instance in _FakeQdrantClient.instances:
        created_fields = {field_name for _collection, field_name in instance.create_payload_index_calls}
        assert expected_fields.issubset(created_fields)
        indexed_collections = {collection for collection, _field in instance.create_payload_index_calls}
        assert {"kb_chunks", "kb_memory", "kb_entities"}.issubset(indexed_collections)


def test_qdrant_query_filter_includes_tags_sources_updated_after(monkeypatch) -> None:
    monkeypatch.setattr("kb_mcp.storage.qdrant_store.QdrantClient", _FakeQdrantClient)
    _FakeQdrantClient.instances.clear()
    _FakeQdrantClient.global_created_indexes.clear()

    store = QdrantVectorStore(
        url="http://fake-qdrant:6333",
        chunks_collection="kb_chunks",
        memory_collection="kb_memory",
        embedder=DeterministicFallbackEmbedder(dimensions=384),
    )
    store.search_chunks(
        query="api contract",
        top_k=5,
        filters={
            "workspace_id": "w1",
            "acl_subject": "u1",
            "acl_roles": ["reader"],
            "tags": ["ext:md"],
            "sources": ["doc_api_contract.md"],
            "updated_after": "2026-02-01T00:00:00Z",
        },
    )
    client = _FakeQdrantClient.instances[-1]
    assert client.last_query_filter is not None
    must_conditions = client.last_query_filter.must or []
    keys = {
        condition.key
        for condition in must_conditions
        if isinstance(condition, models.FieldCondition)
    }
    assert {"workspace_id", "acl_allow", "tags", "source", "updated_at"}.issubset(keys)


def test_qdrant_batches_chunk_embeddings_and_upsert(monkeypatch) -> None:
    monkeypatch.setattr("kb_mcp.storage.qdrant_store.QdrantClient", _FakeQdrantClient)
    _FakeQdrantClient.instances.clear()
    _FakeQdrantClient.global_created_indexes.clear()

    store = QdrantVectorStore(
        url="http://fake-qdrant:6333",
        chunks_collection="kb_chunks",
        memory_collection="kb_memory",
        embedder=DeterministicFallbackEmbedder(dimensions=384),
    )
    store.upsert_chunks(
        chunks=[
            {"chunk_id": "c1", "text": "first", "payload": {"workspace_id": "w1"}},
            {"chunk_id": "c2", "text": "second", "payload": {"workspace_id": "w1"}},
        ]
    )

    points = _FakeQdrantClient.instances[-1].last_upsert_points
    assert len(points) == 2
    assert [point.payload["_item_id"] for point in points if point.payload] == ["c1", "c2"]


def test_qdrant_batches_entity_embeddings_with_workspace_scoped_ids(monkeypatch) -> None:
    monkeypatch.setattr("kb_mcp.storage.qdrant_store.QdrantClient", _FakeQdrantClient)
    _FakeQdrantClient.instances.clear()
    _FakeQdrantClient.global_created_indexes.clear()

    store = QdrantVectorStore(
        url="http://fake-qdrant:6333",
        chunks_collection="kb_chunks",
        memory_collection="kb_memory",
        entities_collection="kb_entities",
        embedder=DeterministicFallbackEmbedder(dimensions=384),
    )
    store.upsert_entities(
        entities=[
            {
                "entity_id": "kb://entity/auth",
                "text": "AuthService login_module",
                "payload": {
                    "workspace_id": "w1",
                    "acl_allow": ["u1"],
                    "name": "AuthService",
                    "aliases": ["login_module"],
                },
            }
        ]
    )

    client = _FakeQdrantClient.instances[-1]
    assert client.last_upsert_collection == "kb_entities"
    assert len(client.last_upsert_points) == 1
    point = client.last_upsert_points[0]
    assert point.payload is not None
    assert point.payload["_item_id"] == "kb://entity/auth"
    assert point.payload["workspace_id"] == "w1"
