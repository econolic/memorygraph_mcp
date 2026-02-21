from __future__ import annotations

from kb_mcp.retrieval.hybrid import HybridRetriever
from kb_mcp.retrieval.models import GraphEdge, GraphNode
from kb_mcp.retrieval.rerank import CrossEncoderReranker, RerankConfig
from kb_mcp.storage.in_memory_vector import InMemoryVectorStore


class FailingGraphStore:
    def resolve_entities(self, *, query: str, filters: dict[str, object]) -> list[str]:
        raise RuntimeError("neo4j unavailable")

    def expand(
        self,
        *,
        seed_uris: list[str],
        depth: int,
        edge_types: list[str],
        max_nodes: int,
        filters: dict[str, object],
    ) -> tuple[list[GraphNode], list[GraphEdge]]:
        raise RuntimeError("neo4j unavailable")

    def explain_uri(self, *, uri: str, filters: dict[str, object]) -> list[str]:
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
        return None

    def upsert_memory_links(self, *, memory_uri: str, entity_uris: list[str], workspace_id: str) -> None:
        return None

    def delete_memory_nodes(self, *, memory_uris: list[str], filters: dict[str, object]) -> int:
        return 0

    def delete_chunks(self, *, chunk_uris: list[str], filters: dict[str, object]) -> int:
        return 0

    def upsert_entity_relations(
        self,
        *,
        relations: list[dict[str, str]],
        workspace_id: str,
        acl_allow: list[str],
    ) -> None:
        return None


def test_graph_failure_fallbacks_to_vector() -> None:
    vector = InMemoryVectorStore()
    vector.upsert_chunk(
        chunk_id="ch1",
        text="lagerid mapping in plan and fact tables",
        payload={"workspace_id": "w1", "acl_allow": ["u1"]},
    )

    retriever = HybridRetriever(
        vector_store=vector,
        graph_store=FailingGraphStore(),
        reranker=CrossEncoderReranker(),
    )
    results, debug = retriever.search(
        query="lagerid plan",
        top_k=5,
        filters={"workspace_id": "w1", "acl_subject": "u1"},
        depth=2,
        edge_types=["DEPENDS_ON"],
        max_nodes=20,
        rerank=RerankConfig(enabled=False),
    )

    assert results
    assert debug.fallback_mode == "vector"
