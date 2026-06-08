from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

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

    @staticmethod
    def _lexical_score(query: str, text: str) -> float:
        normalized_query = query.strip().lower()
        normalized_text = text.strip().lower()
        if not normalized_query or not normalized_text:
            return 0.0
        if normalized_query in normalized_text:
            return 1.0
        tokens = {token for token in normalized_query.replace("-", " ").split() if len(token) > 1}
        if not tokens:
            return 0.0
        matches = sum(1 for token in tokens if token in normalized_text)
        return matches / len(tokens)

    def _search_metadata(
        self,
        *,
        query: str,
        workspace_id: str,
        subject: str,
        top_k: int,
    ) -> list[MemoryHit]:
        ranked: list[tuple[float, dict[str, object]]] = []
        for item in self._metadata.list_memory(workspace_id=workspace_id, subject=subject):
            score = self._lexical_score(query, str(item.get("text", "")))
            if score > 0:
                ranked.append((score, item))
        ranked.sort(key=pair_sort_key, reverse=True)
        out: list[MemoryHit] = []
        for score, item in ranked[:top_k]:
            citations_raw = item.get("citations", [])
            out.append(
                MemoryHit(
                    uri=str(item.get("uri", "")),
                    score=score,
                    text=str(item.get("text", "")),
                    citations=citations_raw if isinstance(citations_raw, list) else [],
                )
            )
        return out

    def upsert(
        self,
        *,
        workspace_id: str,
        subject: str,
        session_id: str,
        items: list[dict[str, object]],
        idempotency_key: str | None = None,
    ) -> tuple[list[str], dict[str, list[str]]]:
        import hashlib
        import json

        scoped_idempotency_key = None
        if idempotency_key:
            payload_str = json.dumps([item for item in items], sort_keys=True)
            composite_key = f"{workspace_id}:{subject}:{idempotency_key}:{payload_str}"
            scoped_idempotency_key = hashlib.sha256(composite_key.encode("utf-8")).hexdigest()
            cached = self._metadata.get_idempotency(scoped_idempotency_key)
            if cached is not None:
                return cached.get("stored_ids", []), cached.get("validation_report", {})

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

        if scoped_idempotency_key:
            self._metadata.set_idempotency(
                scoped_idempotency_key,
                {"stored_ids": stored_ids, "validation_report": reports}
            )

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
        if not out:
            return self._search_metadata(query=query, workspace_id=workspace_id, subject=subject, top_k=top_k)
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


def pair_sort_key(pair: tuple[float, dict[str, Any]]) -> float:
    return pair[0]
