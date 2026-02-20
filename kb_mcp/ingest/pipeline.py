from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from kb_mcp.ingest.chunking import chunk_text
from kb_mcp.ingest.connectors.filesystem import FilesystemConnector
from kb_mcp.ingest.connectors.git import GitConnector
from kb_mcp.ingest.entity_extract import entity_display_name, extract_entities, extract_entity_relations
from kb_mcp.retrieval.graph_store import GraphStore
from kb_mcp.retrieval.vector_store import VectorStore
from kb_mcp.storage.metadata_store import MetadataRepository


class IngestionPipeline:
    def __init__(
        self,
        *,
        vector_store: VectorStore,
        graph_store: GraphStore,
        metadata: MetadataRepository,
        filesystem: FilesystemConnector,
        git: GitConnector | None = None,
    ) -> None:
        self._vector = vector_store
        self._graph = graph_store
        self._metadata = metadata
        self._filesystem = filesystem
        self._git = git or GitConnector()

    @staticmethod
    def _checksum(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def ingest_git_diff(
        self,
        *,
        root: str,
        workspace_id: str,
        acl_allow: list[str],
        since_ref: str = "HEAD~1",
    ) -> dict[str, int]:
        changed_files = self._git.changed_files(repo_root=root, since_ref=since_ref)
        return self.ingest_filesystem(
            root=root,
            workspace_id=workspace_id,
            acl_allow=acl_allow,
            changed_files=changed_files,
        )

    def ingest_filesystem(
        self,
        *,
        root: str,
        workspace_id: str,
        acl_allow: list[str],
        changed_files: list[str] | None = None,
    ) -> dict[str, int]:
        changed_set = {str(Path(path).resolve()) for path in changed_files} if changed_files else None
        docs = self._filesystem.read_documents(root, include_paths=changed_set)
        created = 0
        updated = 0

        for doc in docs:
            source_path = doc["source_path"]
            text = doc["text"]
            checksum = self._checksum(text)
            prev = self._metadata.get_checksum(workspace_id=workspace_id, source_path=source_path)
            if prev == checksum:
                continue

            doc_id = hashlib.sha1(source_path.encode("utf-8")).hexdigest()[:16]
            doc_uri = f"kb://doc/{doc_id}"
            now_iso = datetime.now(tz=timezone.utc).isoformat()
            doc_payload = {
                "uri": doc_uri,
                "title": doc["title"],
                "source": "filesystem",
                "source_path": source_path,
                "workspace_id": workspace_id,
                "acl_allow": acl_allow,
                "tags": [],
                "updated_at": now_iso,
                "checksum": checksum,
            }
            self._metadata.put_doc(doc_uri, doc_payload)

            old_chunks = self._metadata.list_chunks_by_doc(doc_uri=doc_uri)
            old_chunk_uris = {str(item.get("uri", "")) for item in old_chunks}

            new_chunk_uris: set[str] = set()
            for idx, chunk in enumerate(chunk_text(text)):
                chunk_id = f"{doc_id}_{idx}"
                chunk_uri = f"kb://chunk/{chunk_id}"
                new_chunk_uris.add(chunk_uri)
                chunk_text_value = str(chunk["text"])
                entity_uris = extract_entities(chunk_text_value)
                entity_names = {entity_uri: entity_display_name(entity_uri) for entity_uri in entity_uris}
                for entity_uri, entity_name in entity_names.items():
                    self._metadata.put_entity(
                        entity_uri,
                        {
                            "uri": entity_uri,
                            "workspace_id": workspace_id,
                            "acl_allow": acl_allow,
                            "type": "Entity",
                            "name": entity_name,
                            "aliases": [entity_name],
                            "canonical_key": entity_uri.split("kb://entity/")[-1],
                        },
                    )
                chunk_payload: dict[str, object] = {
                    "workspace_id": workspace_id,
                    "acl_allow": acl_allow,
                    "doc_uri": doc_uri,
                    "source_path": source_path,
                    "entity_uris": entity_uris,
                    "updated_at": now_iso,
                    "text": chunk_text_value,
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
                        "source_path": source_path,
                        "updated_at": now_iso,
                    },
                )
                self._graph.upsert_mentions(
                    doc_uri=doc_uri,
                    chunk_uri=chunk_uri,
                    entity_uris=entity_uris,
                    entity_names=entity_names,
                    workspace_id=workspace_id,
                )
                self._graph.upsert_entity_relations(
                    relations=extract_entity_relations(chunk_text_value, entity_uris),
                    workspace_id=workspace_id,
                )

            stale_chunk_uris = sorted(uri for uri in old_chunk_uris if uri and uri not in new_chunk_uris)
            if stale_chunk_uris:
                stale_chunk_ids = [uri.split("/")[-1] for uri in stale_chunk_uris]
                chunk_filters: dict[str, object] = {"workspace_id": workspace_id}
                self._vector.delete_chunks(chunk_ids=stale_chunk_ids, filters=chunk_filters)
                self._graph.delete_chunks(chunk_uris=stale_chunk_uris, filters=chunk_filters)
                for uri in stale_chunk_uris:
                    self._metadata.delete_chunk(uri=uri)

            if prev is None:
                created += 1
            else:
                updated += 1
            self._metadata.set_checksum(workspace_id=workspace_id, source_path=source_path, checksum=checksum)

        return {"created": created, "updated": updated}
