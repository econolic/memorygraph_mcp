from __future__ import annotations

from dataclasses import dataclass

from kb_mcp.retrieval.hybrid import HybridRetriever
from kb_mcp.retrieval.models import GraphNode, VectorHit
from kb_mcp.retrieval.rerank import RerankConfig
from kb_mcp.storage.neo4j_store import Neo4jGraphStore


class _FakeNeo4jDriver:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def execute_query(self, query: str, **kwargs):  # noqa: ANN003
        params = kwargs.get("parameters_", {})
        self.calls.append({"query": query, "parameters": params})
        if "RETURN e.uri AS uri" in query:
            return ([{"uri": "kb://entity/symbol:servicea"}], None, None)
        return ([], None, None)

    def close(self) -> None:
        return None


def test_neo4j_resolve_entities_uses_tokenized_query(monkeypatch) -> None:
    fake_driver = _FakeNeo4jDriver()
    monkeypatch.setattr(
        "kb_mcp.storage.neo4j_store.GraphDatabase.driver",
        lambda uri, auth: fake_driver,  # noqa: ARG005
    )

    store = Neo4jGraphStore(uri="bolt://unused", user="neo4j", password="secret", database="neo4j")
    uris = store.resolve_entities(
        query="entity extraction aliases stoplist dedup precision",
        filters={"workspace_id": "w1", "acl_subject": "u1", "graph_enforce_object_acl": True},
    )
    assert uris == ["kb://entity/symbol:servicea"]
    assert fake_driver.calls
    params = fake_driver.calls[0]["parameters"]
    assert isinstance(params, dict)
    tokens = params.get("tokens")
    assert tokens == ["entity", "extraction", "aliases", "stoplist", "dedup", "precision"]


@dataclass(frozen=True)
class _DummyReranker:
    def rerank(self, *, query: str, items: list, top_n: int):  # noqa: ANN001
        _ = query
        return items[:top_n]


@dataclass(frozen=True)
class _DummyVectorStore:
    def search_chunks(self, *, query: str, top_k: int, filters: dict[str, object]) -> list[VectorHit]:
        _ = query
        _ = filters
        return [
            VectorHit(item_id="c1", score=0.9, payload={"text": "ServiceA depends on ServiceB"}),
            VectorHit(item_id="c2", score=0.4, payload={"text": "misc"}),
        ][:top_k]

    def search_memory(self, *, query: str, top_k: int, filters: dict[str, object]) -> list[VectorHit]:
        _ = query
        _ = top_k
        _ = filters
        return []

    def upsert_chunk(self, *, chunk_id: str, text: str, payload: dict[str, object]) -> None:
        _ = chunk_id
        _ = text
        _ = payload

    def upsert_memory(self, *, memory_id: str, text: str, payload: dict[str, object]) -> None:
        _ = memory_id
        _ = text
        _ = payload

    def delete_memory(self, *, memory_ids: list[str], filters: dict[str, object]) -> int:
        _ = memory_ids
        _ = filters
        return 0

    def delete_chunks(self, *, chunk_ids: list[str], filters: dict[str, object]) -> int:
        _ = chunk_ids
        _ = filters
        return 0


@dataclass(frozen=True)
class _DummyGraphStore:
    def resolve_entities(self, *, query: str, filters: dict[str, object]) -> list[str]:
        _ = query
        _ = filters
        return ["kb://entity/symbol:servicea"]

    def expand(
        self,
        *,
        seed_uris: list[str],
        depth: int,
        edge_types: list[str],
        max_nodes: int,
        filters: dict[str, object],
    ):
        _ = seed_uris
        _ = depth
        _ = edge_types
        _ = max_nodes
        _ = filters
        return ([GraphNode(uri="kb://chunk/c1", type="Chunk", name="c1", properties={})], [])

    def explain_uri(self, *, uri: str, filters: dict[str, object]) -> list[str]:
        _ = uri
        _ = filters
        return []

    def upsert_mentions(
        self,
        *,
        doc_uri: str,
        chunk_uri: str,
        entity_uris: list[str],
        entity_names: dict[str, str],
        workspace_id: str,
        acl_allow: list[str],
    ) -> None:
        _ = doc_uri
        _ = chunk_uri
        _ = entity_uris
        _ = entity_names
        _ = workspace_id
        _ = acl_allow

    def upsert_memory_links(self, *, memory_uri: str, entity_uris: list[str], workspace_id: str) -> None:
        _ = memory_uri
        _ = entity_uris
        _ = workspace_id

    def delete_memory_nodes(self, *, memory_uris: list[str], filters: dict[str, object]) -> int:
        _ = memory_uris
        _ = filters
        return 0

    def delete_chunks(self, *, chunk_uris: list[str], filters: dict[str, object]) -> int:
        _ = chunk_uris
        _ = filters
        return 0

    def upsert_entity_relations(
        self,
        *,
        relations: list[dict[str, str]],
        workspace_id: str,
        acl_allow: list[str],
    ) -> None:
        _ = relations
        _ = workspace_id
        _ = acl_allow


def test_hybrid_retriever_reports_graph_signal_debug_fields() -> None:
    retriever = HybridRetriever(
        vector_store=_DummyVectorStore(),
        graph_store=_DummyGraphStore(),
        reranker=_DummyReranker(),  # type: ignore[arg-type]
        fusion_mode="linear",
    )
    items, debug = retriever.search(
        query="ServiceA depends on ServiceB",
        top_k=2,
        filters={"workspace_id": "w1", "acl_subject": "u1"},
        depth=1,
        edge_types=[],
        max_nodes=32,
        rerank=RerankConfig(enabled=False, top_n=2),
    )
    assert items
    assert items[0].score_breakdown.get("graph", 0.0) > 0.0
    assert debug.graph_seed_count == 1
    assert debug.graph_node_count == 1
    assert debug.graph_chunk_bonus_count == 1
    assert debug.graph_nonzero is True
