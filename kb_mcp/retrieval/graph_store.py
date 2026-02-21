from __future__ import annotations

from typing import Protocol

from kb_mcp.retrieval.models import GraphEdge, GraphNode


class GraphStore(Protocol):
    def resolve_entities(self, *, query: str, filters: dict[str, object]) -> list[str]:
        raise NotImplementedError

    def expand(
        self,
        *,
        seed_uris: list[str],
        depth: int,
        edge_types: list[str],
        max_nodes: int,
        filters: dict[str, object],
    ) -> tuple[list[GraphNode], list[GraphEdge]]:
        raise NotImplementedError

    def explain_uri(self, *, uri: str, filters: dict[str, object]) -> list[str]:
        raise NotImplementedError

    def upsert_mentions(
        self,
        *,
        doc_uri: str,
        chunk_uri: str,
        entity_uris: list[str],
        entity_names: dict[str, str],
        workspace_id: str,
        acl_allow: list[str],
    ) -> None:
        raise NotImplementedError

    def upsert_memory_links(self, *, memory_uri: str, entity_uris: list[str], workspace_id: str) -> None:
        raise NotImplementedError

    def delete_memory_nodes(self, *, memory_uris: list[str], filters: dict[str, object]) -> int:
        raise NotImplementedError

    def delete_chunks(self, *, chunk_uris: list[str], filters: dict[str, object]) -> int:
        raise NotImplementedError

    def upsert_entity_relations(
        self,
        *,
        relations: list[dict[str, str]],
        workspace_id: str,
        acl_allow: list[str],
    ) -> None:
        raise NotImplementedError
