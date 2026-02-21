from __future__ import annotations

from pathlib import Path

from kb_mcp.ingest.connectors.filesystem import FilesystemConnector
from kb_mcp.ingest.pipeline import IngestionPipeline
from kb_mcp.storage.in_memory_graph import InMemoryGraphStore
from kb_mcp.storage.in_memory_vector import InMemoryVectorStore
from kb_mcp.storage.metadata_store import MetadataStore


def test_ingestion_creates_document_chunk_entity_edges(tmp_path: Path) -> None:
    graph = InMemoryGraphStore()
    pipeline = IngestionPipeline(
        vector_store=InMemoryVectorStore(),
        graph_store=graph,
        metadata=MetadataStore(),
        filesystem=FilesystemConnector(),
    )

    file_path = tmp_path / "doc.md"
    file_path.write_text("ServiceA depends on ServiceB in pipeline X.", encoding="utf-8")

    result = pipeline.ingest_filesystem(root=str(tmp_path), workspace_id="w1", acl_allow=["u1"])
    assert result["created"] == 1

    seed = graph.resolve_entities(query="ServiceA", filters={"workspace_id": "w1", "acl_subject": "u1"})
    assert seed
    _nodes, edges = graph.expand(
        seed_uris=seed,
        depth=2,
        edge_types=[],
        max_nodes=200,
        filters={"workspace_id": "w1", "acl_subject": "u1"},
    )
    rels = {edge.rel for edge in edges}
    assert "MENTIONS" in rels
    assert "DOCUMENTED_IN" in rels


def test_ingestion_merges_entity_aliases_and_domain_relations(tmp_path: Path) -> None:
    metadata = MetadataStore()
    graph = InMemoryGraphStore()
    pipeline = IngestionPipeline(
        vector_store=InMemoryVectorStore(),
        graph_store=graph,
        metadata=metadata,
        filesystem=FilesystemConnector(),
    )

    file_path = tmp_path / "doc.md"
    file_path.write_text(
        "Alpha Beta ServiceA depends on ServiceB.\nserviceA depends on ServiceB again.",
        encoding="utf-8",
    )
    result = pipeline.ingest_filesystem(root=str(tmp_path), workspace_id="w1", acl_allow=["u1"])
    assert result["created"] == 1

    entity = metadata.get_entity("kb://entity/symbol:servicea")
    assert isinstance(entity, dict)
    aliases = entity.get("aliases", [])
    assert isinstance(aliases, list)
    assert "ServiceA" in aliases
    assert "serviceA" in aliases

    seeds = graph.resolve_entities(query="ServiceA", filters={"workspace_id": "w1", "acl_subject": "u1"})
    assert seeds
    _nodes, edges = graph.expand(
        seed_uris=seeds,
        depth=2,
        edge_types=[],
        max_nodes=200,
        filters={"workspace_id": "w1", "acl_subject": "u1"},
    )
    assert any(edge.rel == "DEPENDS_ON" for edge in edges)
