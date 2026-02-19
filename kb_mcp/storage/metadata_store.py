from __future__ import annotations

from typing import Any


class MetadataStore:
    def __init__(self) -> None:
        self._docs: dict[str, dict[str, Any]] = {}
        self._chunks: dict[str, dict[str, Any]] = {}
        self._entities: dict[str, dict[str, Any]] = {}
        self._memory: dict[str, dict[str, Any]] = {}

    def put_doc(self, uri: str, data: dict[str, Any]) -> None:
        self._docs[uri] = data

    def put_chunk(self, uri: str, data: dict[str, Any]) -> None:
        self._chunks[uri] = data

    def put_entity(self, uri: str, data: dict[str, Any]) -> None:
        self._entities[uri] = data

    def put_memory(self, uri: str, data: dict[str, Any]) -> None:
        self._memory[uri] = data

    def get_doc(self, uri: str) -> dict[str, Any] | None:
        return self._docs.get(uri)

    def get_chunk(self, uri: str) -> dict[str, Any] | None:
        return self._chunks.get(uri)

    def get_entity(self, uri: str) -> dict[str, Any] | None:
        return self._entities.get(uri)

    def get_memory(self, uri: str) -> dict[str, Any] | None:
        return self._memory.get(uri)

    def delete_memory(self, uri: str) -> bool:
        return self._memory.pop(uri, None) is not None

    def list_memory(self, *, workspace_id: str, subject: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for item in self._memory.values():
            if item.get("workspace_id") == workspace_id and item.get("subject") == subject:
                out.append(item)
        return out
