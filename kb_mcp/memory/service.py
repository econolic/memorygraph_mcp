from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from kb_mcp.memory.validator import MemoryFactValidator, ValidationResult
from kb_mcp.retrieval.vector_store import VectorStore
from kb_mcp.retrieval.graph_store import GraphStore
from kb_mcp.storage.metadata_store import MetadataRepository


@dataclass(frozen=True)
class MemoryHit:
    uri: str
    score: float
    text: str
    citations: list[dict[str, object]]


class MemoryService:
    def __init__(
        self,
        *,
        vector_store: VectorStore,
        graph_store: GraphStore,
        metadata: MetadataRepository,
        validator: MemoryFactValidator,
    ) -> None:
        self._vector = vector_store
        self._graph = graph_store
        self._metadata = metadata
        self._validator = validator

    def upsert(
        self,
        *,
        workspace_id: str,
        subject: str,
        session_id: str,
        items: list[dict[str, object]],
    ) -> tuple[list[str], dict[str, list[str]]]:
        stored_ids: list[str] = []
        reports: dict[str, list[str]] = {}

        for item in items:
            memory_type = str(item.get("type", "summary"))
            text = str(item.get("text", ""))
            citations_raw = item.get("citations", [])
            citations = citations_raw if isinstance(citations_raw, list) else []
            confidence_raw = item.get("confidence", 0.0)
            confidence = float(confidence_raw) if isinstance(confidence_raw, (int, float, str)) else 0.0
            entity_uris_raw = item.get("entity_uris", [])
            entity_uris = (
                [str(uri) for uri in entity_uris_raw]
                if isinstance(entity_uris_raw, list)
                else []
            )

            result: ValidationResult = self._validator.validate(
                memory_type=memory_type,
                text=text,
                citations=citations,
                confidence=confidence,
            )
            if not result.ok:
                reports[text[:40]] = result.reasons
                continue

            memory_id = str(uuid.uuid4())
            memory_uri = f"kb://memory/{memory_id}"
            payload: dict[str, object] = {
                "workspace_id": workspace_id,
                "subject": subject,
                "session_id": session_id,
                "type": memory_type,
                "acl_allow": [subject],
                "updated_at": datetime.now(tz=timezone.utc).isoformat(),
            }
            self._vector.upsert_memory(memory_id=memory_id, text=text, payload=payload)
            self._metadata.put_memory(
                memory_uri,
                {
                    "uri": memory_uri,
                    "workspace_id": workspace_id,
                    "subject": subject,
                    "session_id": session_id,
                    "type": memory_type,
                    "text": text,
                    "citations": citations,
                    "confidence": confidence,
                    "entity_uris": entity_uris,
                },
            )
            self._graph.upsert_memory_links(
                memory_uri=memory_uri,
                entity_uris=entity_uris,
                workspace_id=workspace_id,
            )
            stored_ids.append(memory_id)

        return stored_ids, reports

    def search(
        self,
        *,
        query: str,
        workspace_id: str,
        subject: str,
        top_k: int,
    ) -> list[MemoryHit]:
        filters: dict[str, object] = {"workspace_id": workspace_id, "acl_subject": subject}
        hits = self._vector.search_memory(query=query, top_k=top_k, filters=filters)
        out: list[MemoryHit] = []
        for hit in hits:
            uri = f"kb://memory/{hit.item_id}"
            memory = self._metadata.get_memory(uri)
            if memory is None:
                continue
            out.append(
                MemoryHit(
                    uri=uri,
                    score=hit.score,
                    text=str(memory.get("text", "")),
                    citations=list(memory.get("citations", [])) if isinstance(memory.get("citations"), list) else [],
                )
            )
        return out

    def delete(
        self,
        *,
        workspace_id: str,
        subject: str,
        ids: list[str],
        all_for_subject: bool,
    ) -> int:
        if all_for_subject:
            items = self._metadata.list_memory(workspace_id=workspace_id, subject=subject)
            ids = [str(item["uri"]).split("/")[-1] for item in items]

        filters: dict[str, object] = {"workspace_id": workspace_id, "acl_subject": subject}
        deleted_vector = self._vector.delete_memory(memory_ids=ids, filters=filters)

        memory_uris = [f"kb://memory/{memory_id}" for memory_id in ids]
        self._graph.delete_memory_nodes(memory_uris=memory_uris, filters=filters)

        deleted_metadata = 0
        for uri in memory_uris:
            if self._metadata.delete_memory(uri):
                deleted_metadata += 1

        return min(deleted_vector, deleted_metadata) if deleted_metadata else deleted_vector
