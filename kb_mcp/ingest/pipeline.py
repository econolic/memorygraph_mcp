from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from kb_mcp.ingest.chunking import chunk_text
from kb_mcp.ingest.connectors.filesystem import FilesystemConnector
from kb_mcp.ingest.entity_extract import extract_entities
from kb_mcp.retrieval.graph_store import GraphStore
from kb_mcp.retrieval.vector_store import VectorStore
from kb_mcp.storage.metadata_store import MetadataStore


class IngestionPipeline:
    def __init__(
        self,
        *,
        vector_store: VectorStore,
        graph_store: GraphStore,
        metadata: MetadataStore,
        filesystem: FilesystemConnector,
    ) -> None:
        self._vector = vector_store
        self._graph = graph_store
        self._metadata = metadata
        self._filesystem = filesystem
        self._checksums: dict[str, str] = {}

    @staticmethod
    def _checksum(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def ingest_filesystem(self, *, root: str, workspace_id: str, acl_allow: list[str]) -> dict[str, int]:
        docs = self._filesystem.read_documents(root)
        created = 0
        updated = 0

        for doc in docs:
            source_path = doc["source_path"]
            text = doc["text"]
            checksum = self._checksum(text)
            prev = self._checksums.get(source_path)
            if prev == checksum:
                continue

            doc_id = hashlib.sha1(source_path.encode("utf-8")).hexdigest()[:16]
            doc_uri = f"kb://doc/{doc_id}"
            doc_payload = {
                "uri": doc_uri,
                "title": doc["title"],
                "source_path": source_path,
                "workspace_id": workspace_id,
                "acl_allow": acl_allow,
                "updated_at": datetime.now(tz=timezone.utc).isoformat(),
                "checksum": checksum,
            }
            self._metadata.put_doc(doc_uri, doc_payload)

            for idx, chunk in enumerate(chunk_text(text)):
                chunk_id = f"{doc_id}_{idx}"
                chunk_uri = f"kb://chunk/{chunk_id}"
                chunk_text_value = str(chunk["text"])
                entity_uris = extract_entities(chunk_text_value)
                chunk_payload: dict[str, object] = {
                    "workspace_id": workspace_id,
                    "acl_allow": acl_allow,
                    "doc_uri": doc_uri,
                    "source_path": source_path,
                    "entity_uris": entity_uris,
                    "updated_at": doc_payload["updated_at"],
                }
                self._vector.upsert_chunk(chunk_id=chunk_id, text=chunk_text_value, payload=chunk_payload)
                self._metadata.put_chunk(
                    chunk_uri,
                    {
                        "uri": chunk_uri,
                        "doc_uri": doc_uri,
                        "text": chunk_text_value,
                        "span": chunk["span"],
                        "entity_uris": entity_uris,
                        "workspace_id": workspace_id,
                        "acl_allow": acl_allow,
                    },
                )
                self._graph.upsert_mentions(
                    chunk_uri=chunk_uri,
                    entity_uris=entity_uris,
                    workspace_id=workspace_id,
                )

            if prev is None:
                created += 1
            else:
                updated += 1
            self._checksums[source_path] = checksum

        return {"created": created, "updated": updated}
