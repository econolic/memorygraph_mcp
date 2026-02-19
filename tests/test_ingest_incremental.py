from __future__ import annotations

from pathlib import Path

from kb_mcp.ingest.connectors.filesystem import FilesystemConnector
from kb_mcp.ingest.pipeline import IngestionPipeline
from kb_mcp.storage.in_memory_graph import InMemoryGraphStore
from kb_mcp.storage.in_memory_vector import InMemoryVectorStore
from kb_mcp.storage.metadata_store import MetadataStore


def test_incremental_ingestion(tmp_path: Path) -> None:
    file_path = tmp_path / "doc.md"
    file_path.write_text("first content", encoding="utf-8")

    pipeline = IngestionPipeline(
        vector_store=InMemoryVectorStore(),
        graph_store=InMemoryGraphStore(),
        metadata=MetadataStore(),
        filesystem=FilesystemConnector(),
    )

    first = pipeline.ingest_filesystem(root=str(tmp_path), workspace_id="w1", acl_allow=["u1"])
    second = pipeline.ingest_filesystem(root=str(tmp_path), workspace_id="w1", acl_allow=["u1"])

    assert first["created"] == 1
    assert second["created"] == 0
    assert second["updated"] == 0

    file_path.write_text("first content updated", encoding="utf-8")
    third = pipeline.ingest_filesystem(root=str(tmp_path), workspace_id="w1", acl_allow=["u1"])
    assert third["updated"] == 1
