from __future__ import annotations

from pathlib import Path

from kb_mcp.ingest.connectors.filesystem import FilesystemConnector
from kb_mcp.ingest.pipeline import IngestionPipeline
from kb_mcp.storage.in_memory_graph import InMemoryGraphStore
from kb_mcp.storage.in_memory_vector import InMemoryVectorStore
from kb_mcp.storage.sql_metadata_store import SQLMetadataStore


def test_checksums_persist_across_pipeline_instances(tmp_path: Path) -> None:
    doc = tmp_path / "doc.md"
    doc.write_text("stable content", encoding="utf-8")
    db_path = tmp_path / "metadata.db"
    dsn = f"sqlite:///{db_path}"

    pipeline_1 = IngestionPipeline(
        vector_store=InMemoryVectorStore(),
        graph_store=InMemoryGraphStore(),
        metadata=SQLMetadataStore(dsn=dsn),
        filesystem=FilesystemConnector(),
    )
    first = pipeline_1.ingest_filesystem(root=str(tmp_path), workspace_id="w1", acl_allow=["u1"])
    assert first["created"] == 1

    pipeline_2 = IngestionPipeline(
        vector_store=InMemoryVectorStore(),
        graph_store=InMemoryGraphStore(),
        metadata=SQLMetadataStore(dsn=dsn),
        filesystem=FilesystemConnector(),
    )
    second = pipeline_2.ingest_filesystem(root=str(tmp_path), workspace_id="w1", acl_allow=["u1"])
    assert second["created"] == 0
    assert second["updated"] == 0
