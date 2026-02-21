from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from kb_mcp.retrieval.models import VectorHit


@dataclass
class _VectorItem:
    item_id: str
    text: str
    payload: dict[str, object]


class InMemoryVectorStore:
    def __init__(self) -> None:
        self._chunks: dict[str, _VectorItem] = {}
        self._memory: dict[str, _VectorItem] = {}

    def _score(self, query: str, text: str) -> float:
        q = set(query.lower().split())
        t = set(text.lower().split())
        if not q:
            return 0.0
        return len(q & t) / len(q)

    @staticmethod
    def _to_utc_datetime(value: object) -> datetime | None:
        if isinstance(value, datetime):
            dt = value
        elif isinstance(value, str) and value.strip():
            raw = value.strip()
            if raw.endswith("Z"):
                raw = f"{raw[:-1]}+00:00"
            try:
                dt = datetime.fromisoformat(raw)
            except ValueError:
                return None
        else:
            return None

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def _matches_filter(self, payload: dict[str, object], filters: dict[str, object]) -> bool:
        workspace_id = str(filters.get("workspace_id", ""))
        acl_subject = str(filters.get("acl_subject", ""))
        acl_roles_raw = filters.get("acl_roles", [])
        acl_roles = (
            [f"role:{str(role).strip()}" for role in acl_roles_raw if str(role).strip()]
            if isinstance(acl_roles_raw, list)
            else []
        )
        tags_raw = filters.get("tags", [])
        tags_filter = (
            [str(tag).strip() for tag in tags_raw if str(tag).strip()]
            if isinstance(tags_raw, list)
            else []
        )
        sources_raw = filters.get("sources", [])
        sources_filter = (
            [str(source).strip() for source in sources_raw if str(source).strip()]
            if isinstance(sources_raw, list)
            else []
        )
        updated_after = self._to_utc_datetime(filters.get("updated_after"))

        if workspace_id and payload.get("workspace_id") != workspace_id:
            return False
        allow = payload.get("acl_allow", [])
        if acl_subject:
            if not isinstance(allow, list) or not allow:
                return False
            allow_values = {str(item) for item in allow}
            if acl_subject not in allow_values and not any(role in allow_values for role in acl_roles):
                return False
        if tags_filter:
            payload_tags_raw = payload.get("tags", [])
            payload_tags = (
                {str(tag).strip() for tag in payload_tags_raw if str(tag).strip()}
                if isinstance(payload_tags_raw, list)
                else set()
            )
            if not payload_tags.intersection(tags_filter):
                return False
        if sources_filter:
            source = str(payload.get("source", "")).strip()
            if source not in set(sources_filter):
                return False
        if updated_after is not None:
            item_updated_at = self._to_utc_datetime(payload.get("updated_at"))
            if item_updated_at is None or item_updated_at < updated_after:
                return False
        return True

    def search_chunks(self, *, query: str, top_k: int, filters: dict[str, object]) -> list[VectorHit]:
        scored = [
            VectorHit(item_id=item.item_id, score=self._score(query, item.text), payload=item.payload)
            for item in self._chunks.values()
            if self._matches_filter(item.payload, filters)
        ]
        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_k]

    def search_memory(self, *, query: str, top_k: int, filters: dict[str, object]) -> list[VectorHit]:
        scored = [
            VectorHit(item_id=item.item_id, score=self._score(query, item.text), payload=item.payload)
            for item in self._memory.values()
            if self._matches_filter(item.payload, filters)
        ]
        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_k]

    def upsert_chunk(self, *, chunk_id: str, text: str, payload: dict[str, object]) -> None:
        self._chunks[chunk_id] = _VectorItem(item_id=chunk_id, text=text, payload=payload)

    def upsert_memory(self, *, memory_id: str, text: str, payload: dict[str, object]) -> None:
        self._memory[memory_id] = _VectorItem(item_id=memory_id, text=text, payload=payload)

    def delete_memory(self, *, memory_ids: list[str], filters: dict[str, object]) -> int:
        deleted = 0
        for memory_id in memory_ids:
            item = self._memory.get(memory_id)
            if item is None:
                continue
            if self._matches_filter(item.payload, filters):
                del self._memory[memory_id]
                deleted += 1
        return deleted

    def delete_chunks(self, *, chunk_ids: list[str], filters: dict[str, object]) -> int:
        deleted = 0
        for chunk_id in chunk_ids:
            item = self._chunks.get(chunk_id)
            if item is None:
                continue
            if self._matches_filter(item.payload, filters):
                del self._chunks[chunk_id]
                deleted += 1
        return deleted
