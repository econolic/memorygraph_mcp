from __future__ import annotations

from collections import defaultdict

from kb_mcp.retrieval.models import GraphEdge, GraphNode


class InMemoryGraphStore:
    def __init__(self) -> None:
        self._nodes: dict[str, GraphNode] = {}
        self._edges: list[GraphEdge] = []
        self._mentions: dict[str, list[str]] = defaultdict(list)

    def _workspace_allows(self, uri: str, workspace_id: str) -> bool:
        node = self._nodes.get(uri)
        if node is None:
            return False
        return str(node.properties.get("workspace_id", "")) == workspace_id

    def resolve_entities(self, *, query: str, filters: dict[str, object]) -> list[str]:
        tokens = set(query.lower().split())
        workspace_id = str(filters.get("workspace_id", ""))
        out: list[str] = []
        for uri, node in self._nodes.items():
            if node.type != "Entity":
                continue
            if workspace_id and str(node.properties.get("workspace_id", "")) != workspace_id:
                continue
            name_tokens = set(node.name.lower().split())
            canonical = str(node.properties.get("canonical_key", "")).lower()
            aliases_raw = node.properties.get("aliases", [])
            aliases = [str(alias).lower() for alias in aliases_raw] if isinstance(aliases_raw, list) else []
            if tokens & name_tokens or any(token in canonical for token in tokens):
                out.append(uri)
                continue
            if any(any(token in alias for token in tokens) for alias in aliases):
                out.append(uri)
        return out[:20]

    def expand(
        self,
        *,
        seed_uris: list[str],
        depth: int,
        edge_types: list[str],
        max_nodes: int,
        filters: dict[str, object],
    ) -> tuple[list[GraphNode], list[GraphEdge]]:
        workspace_id = str(filters.get("workspace_id", ""))
        allowed = set(edge_types)
        visited = {uri for uri in seed_uris if self._workspace_allows(uri, workspace_id)}
        frontier = list(visited)
        out_edges: list[GraphEdge] = []

        for _ in range(depth):
            next_frontier: list[str] = []
            for edge in self._edges:
                if allowed and edge.rel not in allowed:
                    continue
                if not self._workspace_allows(edge.src, workspace_id):
                    continue
                if not self._workspace_allows(edge.dst, workspace_id):
                    continue
                if edge.src in frontier and edge.dst not in visited:
                    visited.add(edge.dst)
                    next_frontier.append(edge.dst)
                    out_edges.append(edge)
                if edge.dst in frontier and edge.src not in visited:
                    visited.add(edge.src)
                    next_frontier.append(edge.src)
                    out_edges.append(edge)
                if len(visited) >= max_nodes:
                    break
            frontier = next_frontier
            if not frontier or len(visited) >= max_nodes:
                break

        nodes = [self._nodes[uri] for uri in visited if uri in self._nodes]
        return nodes, out_edges

    def explain_uri(self, *, uri: str, filters: dict[str, object]) -> list[str]:
        workspace_id = str(filters.get("workspace_id", ""))
        reasons = []
        node = self._nodes.get(uri)
        if node is not None and str(node.properties.get("workspace_id", "")) == workspace_id:
            reasons.append(f"uri {uri} exists in graph")
        linked = self._mentions.get(uri, [])
        if linked:
            reasons.append(f"linked entities: {', '.join(linked[:5])}")
        return reasons

    def upsert_mentions(
        self,
        *,
        doc_uri: str,
        chunk_uri: str,
        entity_uris: list[str],
        entity_names: dict[str, str],
        workspace_id: str,
    ) -> None:
        if doc_uri not in self._nodes:
            self._nodes[doc_uri] = GraphNode(
                uri=doc_uri,
                type="Document",
                name=doc_uri.split("/")[-1],
                properties={"workspace_id": workspace_id},
            )
        if chunk_uri not in self._nodes:
            self._nodes[chunk_uri] = GraphNode(
                uri=chunk_uri,
                type="Chunk",
                name=chunk_uri.split("/")[-1],
                properties={"workspace_id": workspace_id},
            )
        self._edges.append(GraphEdge(src=doc_uri, rel="CONTAINS", dst=chunk_uri))

        for entity_uri in entity_uris:
            if entity_uri not in self._nodes:
                canonical = entity_uri.split("/")[-1]
                self._nodes[entity_uri] = GraphNode(
                    uri=entity_uri,
                    type="Entity",
                    name=entity_names.get(entity_uri, canonical),
                    properties={
                        "workspace_id": workspace_id,
                        "canonical_key": canonical,
                        "aliases": [entity_names.get(entity_uri, canonical)],
                    },
                )
            self._edges.append(GraphEdge(src=chunk_uri, rel="MENTIONS", dst=entity_uri))
            self._edges.append(GraphEdge(src=entity_uri, rel="DOCUMENTED_IN", dst=doc_uri))
            self._mentions[chunk_uri].append(entity_uri)

    def upsert_memory_links(self, *, memory_uri: str, entity_uris: list[str], workspace_id: str) -> None:
        if memory_uri not in self._nodes:
            self._nodes[memory_uri] = GraphNode(
                uri=memory_uri,
                type="Memory",
                name=memory_uri.split("/")[-1],
                properties={"workspace_id": workspace_id},
            )
        for entity_uri in entity_uris:
            if entity_uri not in self._nodes:
                canonical = entity_uri.split("/")[-1]
                self._nodes[entity_uri] = GraphNode(
                    uri=entity_uri,
                    type="Entity",
                    name=canonical,
                    properties={"workspace_id": workspace_id, "canonical_key": canonical, "aliases": [canonical]},
                )
            self._edges.append(GraphEdge(src=memory_uri, rel="MEMORY_REFERS_TO", dst=entity_uri))

    def delete_memory_nodes(self, *, memory_uris: list[str], filters: dict[str, object]) -> int:
        workspace_id = str(filters.get("workspace_id", ""))
        memory_set = {
            uri for uri in memory_uris
            if uri in self._nodes and str(self._nodes[uri].properties.get("workspace_id", "")) == workspace_id
        }
        if not memory_set:
            return 0
        before = len(self._edges)
        self._nodes = {k: v for k, v in self._nodes.items() if k not in memory_set}
        self._edges = [e for e in self._edges if e.src not in memory_set and e.dst not in memory_set]
        return before - len(self._edges)

    def delete_chunks(self, *, chunk_uris: list[str], filters: dict[str, object]) -> int:
        workspace_id = str(filters.get("workspace_id", ""))
        chunk_set = {
            uri for uri in chunk_uris
            if uri in self._nodes and str(self._nodes[uri].properties.get("workspace_id", "")) == workspace_id
        }
        if not chunk_set:
            return 0
        before = len(self._edges)
        self._nodes = {k: v for k, v in self._nodes.items() if k not in chunk_set}
        self._edges = [e for e in self._edges if e.src not in chunk_set and e.dst not in chunk_set]
        return before - len(self._edges)

    def upsert_entity_relations(self, *, relations: list[dict[str, str]], workspace_id: str) -> None:
        allowed = {"DEPENDS_ON", "CALLS", "OWNS", "IMPLEMENTS", "AFFECTS"}
        for rel in relations:
            src = rel.get("src", "")
            dst = rel.get("dst", "")
            rel_type = rel.get("rel", "")
            if not src or not dst or rel_type not in allowed:
                continue
            if src not in self._nodes:
                self._nodes[src] = GraphNode(
                    uri=src,
                    type="Entity",
                    name=src.split("/")[-1],
                    properties={"workspace_id": workspace_id},
                )
            if dst not in self._nodes:
                self._nodes[dst] = GraphNode(
                    uri=dst,
                    type="Entity",
                    name=dst.split("/")[-1],
                    properties={"workspace_id": workspace_id},
                )
            self._edges.append(GraphEdge(src=src, rel=rel_type, dst=dst))
