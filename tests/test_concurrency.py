from __future__ import annotations

import time
from threading import Thread
from typing import Any

from kb_mcp.ingest.pipeline import IngestionPipeline
from kb_mcp.ingest.embeddings import LocalSentenceTransformerEmbedder
from kb_mcp.retrieval.rerank import CrossEncoderReranker
from kb_mcp.retrieval.models import RetrievedItem

class FakeFilesystemConnector:
    def __init__(self, delay: float = 0.0) -> None:
        self.delay = delay

    def read_documents(self, root: str, include_paths: set[str] | None = None) -> list[dict[str, Any]]:
        if self.delay > 0:
            time.sleep(self.delay)
        return [{"source_path": "test.txt", "text": "hello world", "title": "test", "source": "filesystem"}]

class FakeVectorStore:
    def upsert_chunk(self, chunk_id: str, text: str, payload: dict[str, Any]) -> None:
        pass
    def delete_chunks(self, chunk_ids: list[str], filters: dict[str, Any]) -> int:
        return 0

class FakeGraphStore:
    def upsert_mentions(self, **kwargs: Any) -> None:
        pass
    def upsert_entity_relations(self, **kwargs: Any) -> None:
        pass
    def delete_chunks(self, **kwargs: Any) -> int:
        return 0

class FakeMetadataRepository:
    def get_checksum(self, **kwargs: Any) -> str | None:
        return None
    def put_doc(self, uri: str, payload: dict[str, Any]) -> None:
        pass
    def list_chunks_by_doc(self, doc_uri: str) -> list[Any]:
        return []
    def put_chunk(self, uri: str, payload: dict[str, Any]) -> None:
        pass
    def put_entity(self, uri: str, payload: dict[str, Any]) -> None:
        pass
    def get_entity(self, uri: str) -> dict[str, Any] | None:
        return None
    def get_doc(self, uri: str) -> dict[str, Any] | None:
        return None
    def set_checksum(self, **kwargs: Any) -> None:
        pass

def test_ingestion_pipeline_workspace_locking() -> None:
    # Set up pipeline with a filesystem connector that delays for 0.5s during read_documents
    filesystem = FakeFilesystemConnector(delay=0.5)
    pipeline = IngestionPipeline(
        vector_store=FakeVectorStore(),
        graph_store=FakeGraphStore(),
        metadata=FakeMetadataRepository(),
        filesystem=filesystem,
        chunking_mode="char",
    )

    errors: list[Exception] = []

    def run_ingest(workspace_id: str) -> None:
        try:
            pipeline.ingest_filesystem(
                root=".",
                workspace_id=workspace_id,
                acl_allow=["u1"],
            )
        except Exception as exc:
            errors.append(exc)

    # Start first ingestion on workspace 'w1'
    t1 = Thread(target=run_ingest, args=("w1",))
    t1.start()

    # Sleep slightly to ensure t1 enters ingest_filesystem and acquires lock
    time.sleep(0.1)

    # Start second ingestion on workspace 'w1' - should raise conflict immediately
    t2 = Thread(target=run_ingest, args=("w1",))
    t2.start()

    # Start third ingestion on workspace 'w2' - should succeed without error since it's a different workspace
    t3 = Thread(target=run_ingest, args=("w2",))
    t3.start()

    t1.join()
    t2.join()
    t3.join()

    # We expect exactly one conflict error from t2
    assert len(errors) == 1
    assert "Ingestion for workspace w1 is already in progress" in str(errors[0])

def test_embedder_and_reranker_concurrency_locks() -> None:
    # Just verify embedder and reranker can be called concurrently and don't deadlock
    embedder = LocalSentenceTransformerEmbedder(model_name="all-MiniLM-L6-v2")
    reranker = CrossEncoderReranker(model_name="cross-encoder/ms-marco-MiniLM-L-6-v2")

    # Call concurrently from threads
    errors = []
    def run_concurrent():
        try:
            embedder.embed_query("test query")
            embedder.embed_texts(["text 1", "text 2"])
            reranker.rerank(
                query="test query",
                items=[RetrievedItem(uri="kb://doc/1", text="text 1", score=1.0, score_breakdown={})],
                top_n=5
            )
        except Exception as exc:
            errors.append(exc)

    t1 = Thread(target=run_concurrent)
    t2 = Thread(target=run_concurrent)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors
