from __future__ import annotations

from dataclasses import dataclass

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

    def _matches_filter(self, payload: dict[str, object], filters: dict[str, object]) -> bool:
        workspace_id = str(filters.get("workspace_id", ""))
        acl_subject = str(filters.get("acl_subject", ""))
        if workspace_id and payload.get("workspace_id") != workspace_id:
            return False
        allow = payload.get("acl_allow", [])
        if acl_subject and isinstance(allow, list) and allow and acl_subject not in allow:
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
