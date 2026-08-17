from __future__ import annotations

from typing import Protocol

from kb_mcp.retrieval.models import VectorHit


class VectorStore(Protocol):
    def search_chunks(
        self,
        *,
        query: str,
        top_k: int,
        filters: dict[str, object],
    ) -> list[VectorHit]:
        raise NotImplementedError

    def search_memory(
        self,
        *,
        query: str,
        top_k: int,
        filters: dict[str, object],
    ) -> list[VectorHit]:
        raise NotImplementedError

    def upsert_chunk(
        self,
        *,
        chunk_id: str,
        text: str,
        payload: dict[str, object],
    ) -> None:
        raise NotImplementedError

    def upsert_chunks(self, *, chunks: list[dict[str, object]]) -> None:
        raise NotImplementedError

    def upsert_memory(
        self,
        *,
        memory_id: str,
        text: str,
        payload: dict[str, object],
    ) -> None:
        raise NotImplementedError

    def delete_memory(self, *, memory_ids: list[str], filters: dict[str, object]) -> int:
        raise NotImplementedError

    def delete_chunks(self, *, chunk_ids: list[str], filters: dict[str, object]) -> int:
        raise NotImplementedError
