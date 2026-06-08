from __future__ import annotations

from typing import Any, Protocol


class MetadataRepository(Protocol):
    def put_doc(self, uri: str, data: dict[str, Any]) -> None:
        raise NotImplementedError

    def put_chunk(self, uri: str, data: dict[str, Any]) -> None:
        raise NotImplementedError

    def put_entity(self, uri: str, data: dict[str, Any]) -> None:
        raise NotImplementedError

    def put_memory(self, uri: str, data: dict[str, Any]) -> None:
        raise NotImplementedError

    def get_doc(self, uri: str) -> dict[str, Any] | None:
        raise NotImplementedError

    def get_chunk(self, uri: str) -> dict[str, Any] | None:
        raise NotImplementedError

    def get_entity(self, uri: str) -> dict[str, Any] | None:
        raise NotImplementedError

    def get_memory(self, uri: str) -> dict[str, Any] | None:
        raise NotImplementedError

    def delete_memory(self, uri: str) -> bool:
        raise NotImplementedError

    def list_memory(self, *, workspace_id: str, subject: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    def list_chunks_by_doc(self, *, doc_uri: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    def delete_chunk(self, *, uri: str) -> bool:
        raise NotImplementedError

    def get_checksum(self, *, workspace_id: str, source_path: str) -> str | None:
        raise NotImplementedError

    def set_checksum(self, *, workspace_id: str, source_path: str, checksum: str) -> None:
        raise NotImplementedError

    def list_entities(self, *, workspace_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    def get_idempotency(self, key: str) -> dict[str, Any] | None:
        raise NotImplementedError

    def set_idempotency(self, key: str, result: dict[str, Any]) -> None:
        raise NotImplementedError


class MetadataStore:
    def __init__(self) -> None:
        self._docs: dict[str, dict[str, Any]] = {}
        self._chunks: dict[str, dict[str, Any]] = {}
        self._entities: dict[str, dict[str, Any]] = {}
        self._memory: dict[str, dict[str, Any]] = {}
        self._checksums: dict[tuple[str, str], str] = {}
        self._idempotency: dict[str, dict[str, Any]] = {}

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

    def list_chunks_by_doc(self, *, doc_uri: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for chunk in self._chunks.values():
            if chunk.get("doc_uri") == doc_uri:
                out.append(chunk)
        return out

    def delete_chunk(self, *, uri: str) -> bool:
        return self._chunks.pop(uri, None) is not None

    def get_checksum(self, *, workspace_id: str, source_path: str) -> str | None:
        return self._checksums.get((workspace_id, source_path))

    def set_checksum(self, *, workspace_id: str, source_path: str, checksum: str) -> None:
        self._checksums[(workspace_id, source_path)] = checksum

    def list_entities(self, *, workspace_id: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for item in self._entities.values():
            if item.get("workspace_id") == workspace_id:
                out.append(item)
        return out

    def get_idempotency(self, key: str) -> dict[str, Any] | None:
        return self._idempotency.get(key)

    def set_idempotency(self, key: str, result: dict[str, Any]) -> None:
        self._idempotency[key] = result
