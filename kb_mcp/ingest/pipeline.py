from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from kb_mcp.ingest.chunking import chunk_text
from kb_mcp.ingest.connectors.filesystem import FilesystemConnector
from kb_mcp.ingest.connectors.git import GitConnector
from kb_mcp.ingest.entity_extract import (
    EntityExtractionConfig,
    entity_display_name,
    extract_entities,
    extract_entity_aliases,
    extract_entity_relations,
)
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
        chunking_mode: str = "char",
        entity_config: EntityExtractionConfig | None = None,
        embedding_model_info: dict[str, str] | None = None,
    ) -> None:
        self._vector = vector_store
        self._graph = graph_store
        self._metadata = metadata
        self._filesystem = filesystem
        self._git = git or GitConnector()
        self._chunking_mode = chunking_mode
        self._entity_cfg = entity_config or EntityExtractionConfig()
        self._embedding_model_info = embedding_model_info or {}

    @staticmethod
    def _merge_aliases(existing: object, incoming: list[str]) -> list[str]:
        aliases: list[str] = []
        if isinstance(existing, list):
            for alias in existing:
                value = str(alias).strip()
                if value and value not in aliases:
                    aliases.append(value)
        for alias in incoming:
            value = str(alias).strip()
            if value and value not in aliases:
                aliases.append(value)
        return aliases

    @staticmethod
    def _checksum(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def _legacy_doc_id(source_path: str) -> str:
        return hashlib.sha1(source_path.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _scoped_doc_id(*, workspace_id: str, source_path: str) -> str:
        return hashlib.sha1(f"{workspace_id}:{source_path}".encode("utf-8")).hexdigest()[:16]

    def _choose_doc_identity(self, *, workspace_id: str, source_path: str) -> tuple[str, str]:
        legacy_doc_id = self._legacy_doc_id(source_path)
        legacy_doc_uri = f"kb://doc/{legacy_doc_id}"
        legacy_doc = self._metadata.get_doc(legacy_doc_uri)
        if isinstance(legacy_doc, dict) and str(legacy_doc.get("workspace_id", "")) == workspace_id:
            return legacy_doc_id, legacy_doc_uri

        scoped_doc_id = self._scoped_doc_id(workspace_id=workspace_id, source_path=source_path)
        scoped_doc_uri = f"kb://doc/{scoped_doc_id}"
        return scoped_doc_id, scoped_doc_uri

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
        changed_set = None if changed_files is None else {str(Path(path).resolve()) for path in changed_files}
        docs = self._filesystem.read_documents(root, include_paths=changed_set)
        created = 0
        updated = 0

        for doc in docs:
            source_path = str(doc.get("source_path", ""))
            text = str(doc.get("text", ""))
            title = str(doc.get("title", ""))
            source = str(doc.get("source", "filesystem"))
            tags_raw = doc.get("tags", [])
            tags = [str(v) for v in tags_raw] if isinstance(tags_raw, list) else []
            if not source_path or not text:
                continue
            checksum = self._checksum(text)
            prev = self._metadata.get_checksum(workspace_id=workspace_id, source_path=source_path)
            if prev == checksum:
                continue

            doc_id, doc_uri = self._choose_doc_identity(workspace_id=workspace_id, source_path=source_path)
            now_iso = datetime.now(tz=timezone.utc).isoformat()
            doc_payload = {
                "uri": doc_uri,
                "title": title,
                "source": source,
                "source_path": source_path,
                "workspace_id": workspace_id,
                "acl_allow": acl_allow,
                "tags": tags,
                "updated_at": now_iso,
                "checksum": checksum,
            }
            self._metadata.put_doc(doc_uri, doc_payload)

            old_chunks = self._metadata.list_chunks_by_doc(doc_uri=doc_uri)
            old_chunk_uris = {str(item.get("uri", "")) for item in old_chunks}

            new_chunk_uris: set[str] = set()
            for idx, chunk in enumerate(chunk_text(text, mode=self._chunking_mode)):
                chunk_id = f"{doc_id}_{idx}"
                chunk_uri = f"kb://chunk/{chunk_id}"
                new_chunk_uris.add(chunk_uri)
                chunk_text_value = str(chunk["text"])
                entity_uris = extract_entities(chunk_text_value, cfg=self._entity_cfg)
                entity_aliases = extract_entity_aliases(chunk_text_value, cfg=self._entity_cfg)
                entity_names = {}
                for entity_uri in entity_uris:
                    raw_aliases = entity_aliases.get(entity_uri, [])
                    display_name = raw_aliases[0] if raw_aliases else entity_display_name(entity_uri)
                    existing = self._metadata.get_entity(entity_uri) or {}
                    merged_aliases = self._merge_aliases(
                        existing.get("aliases", []),
                        [display_name, *raw_aliases, entity_display_name(entity_uri)],
                    )
                    canonical_key = str(existing.get("canonical_key", "")).strip() or entity_uri.split(
                        "kb://entity/"
                    )[-1]
                    entity_names[entity_uri] = str(existing.get("name", "")).strip() or display_name
                    self._metadata.put_entity(
                        entity_uri,
                        {
                            "uri": entity_uri,
                            "workspace_id": workspace_id,
                            "acl_allow": acl_allow,
                            "type": "Entity",
                            "name": entity_names[entity_uri],
                            "aliases": merged_aliases,
                            "canonical_key": canonical_key,
                        },
                    )
                chunk_payload: dict[str, object] = {
                    "workspace_id": workspace_id,
                    "acl_allow": acl_allow,
                    "doc_uri": doc_uri,
                    "source": source,
                    "source_path": source_path,
                    "tags": tags,
                    "entity_uris": entity_uris,
                    "updated_at": now_iso,
                    "text": chunk_text_value,
                    "embedding_provider": str(self._embedding_model_info.get("provider", "")),
                    "embedding_model": str(self._embedding_model_info.get("model", "")),
                    "embedding_revision": str(self._embedding_model_info.get("revision", "")),
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
                        "source": source,
                        "source_path": source_path,
                        "tags": tags,
                        "updated_at": now_iso,
                        "embedding_provider": str(self._embedding_model_info.get("provider", "")),
                        "embedding_model": str(self._embedding_model_info.get("model", "")),
                        "embedding_revision": str(self._embedding_model_info.get("revision", "")),
                    },
                )
                self._graph.upsert_mentions(
                    doc_uri=doc_uri,
                    chunk_uri=chunk_uri,
                    entity_uris=entity_uris,
                    entity_names=entity_names,
                    workspace_id=workspace_id,
                    acl_allow=acl_allow,
                )
                self._graph.upsert_entity_relations(
                    relations=extract_entity_relations(chunk_text_value, entity_uris, cfg=self._entity_cfg),
                    workspace_id=workspace_id,
                    acl_allow=acl_allow,
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
