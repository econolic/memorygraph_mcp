from __future__ import annotations

from pathlib import Path
from typing import Any

from kb_mcp.ingest.connectors.filesystem import FilesystemConnector
from kb_mcp.ingest.pipeline import IngestionPipeline
from kb_mcp.storage.in_memory_graph import InMemoryGraphStore
from kb_mcp.storage.in_memory_vector import InMemoryVectorStore
from kb_mcp.storage.metadata_store import MetadataStore


class _BatchTrackingVectorStore(InMemoryVectorStore):
    def __init__(self) -> None:
        super().__init__()
        self.batch_sizes: list[int] = []

    def upsert_chunks(self, *, chunks: list[dict[str, object]]) -> None:
        self.batch_sizes.append(len(chunks))
        super().upsert_chunks(chunks=chunks)


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
    assert second["skipped"] == 1

    file_path.write_text("first content updated", encoding="utf-8")
    third = pipeline.ingest_filesystem(root=str(tmp_path), workspace_id="w1", acl_allow=["u1"])
    assert third["updated"] == 1


def test_ingest_with_empty_changed_files_does_not_fallback_to_full_scan(tmp_path: Path) -> None:
    file_path = tmp_path / "doc.md"
    file_path.write_text("content", encoding="utf-8")

    pipeline = IngestionPipeline(
        vector_store=InMemoryVectorStore(),
        graph_store=InMemoryGraphStore(),
        metadata=MetadataStore(),
        filesystem=FilesystemConnector(),
    )

    first = pipeline.ingest_filesystem(
        root=str(tmp_path),
        workspace_id="w1",
        acl_allow=["u1"],
        changed_files=[],
    )
    second = pipeline.ingest_filesystem(
        root=str(tmp_path),
        workspace_id="w1",
        acl_allow=["u1"],
    )

    assert first["created"] == 0
    assert first["updated"] == 0
    assert second["created"] == 1


def test_changed_file_ingest_does_not_walk_the_repository(
    tmp_path: Path, monkeypatch: Any
) -> None:
    file_path = tmp_path / "doc.md"
    file_path.write_text("targeted content", encoding="utf-8")

    def fail_rglob(_self: Path, _pattern: str) -> object:
        raise AssertionError("targeted ingest must not scan the full repository")

    monkeypatch.setattr(Path, "rglob", fail_rglob)
    docs = FilesystemConnector().read_documents(
        str(tmp_path),
        include_paths={str(file_path.resolve())},
    )

    assert len(docs) == 1
    assert docs[0]["source"] == "doc.md"


def test_changed_file_ingest_rejects_paths_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("must not be read", encoding="utf-8")

    docs = FilesystemConnector().read_documents(
        str(root),
        include_paths={str(outside.resolve())},
    )

    assert docs == []


def test_dry_run_counts_candidates_without_persisting(tmp_path: Path) -> None:
    file_path = tmp_path / "doc.md"
    file_path.write_text("content", encoding="utf-8")
    metadata = MetadataStore()

    pipeline = IngestionPipeline(
        vector_store=InMemoryVectorStore(),
        graph_store=InMemoryGraphStore(),
        metadata=metadata,
        filesystem=FilesystemConnector(),
    )

    dry = pipeline.ingest_filesystem(
        root=str(tmp_path),
        workspace_id="w1",
        acl_allow=["u1"],
        dry_run=True,
    )
    actual = pipeline.ingest_filesystem(root=str(tmp_path), workspace_id="w1", acl_allow=["u1"])

    assert dry["dry_run"] is True
    assert dry["created"] == 1
    assert metadata.list_chunks_by_doc(doc_uri="kb://doc/missing") == []
    assert actual["created"] == 1


def test_ingestion_batches_all_chunks_for_each_document(tmp_path: Path) -> None:
    (tmp_path / "doc.md").write_text("chunk text " * 300, encoding="utf-8")
    vector_store = _BatchTrackingVectorStore()
    pipeline = IngestionPipeline(
        vector_store=vector_store,
        graph_store=InMemoryGraphStore(),
        metadata=MetadataStore(),
        filesystem=FilesystemConnector(),
    )

    pipeline.ingest_filesystem(root=str(tmp_path), workspace_id="w1", acl_allow=["u1"])

    assert len(vector_store.batch_sizes) == 1
    assert vector_store.batch_sizes[0] > 1
