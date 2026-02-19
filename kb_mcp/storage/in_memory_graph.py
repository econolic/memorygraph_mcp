from __future__ import annotations

from collections import defaultdict

from kb_mcp.retrieval.models import GraphEdge, GraphNode


class InMemoryGraphStore:
    def __init__(self) -> None:
        self._nodes: dict[str, GraphNode] = {}
        self._edges: list[GraphEdge] = []
        self._mentions: dict[str, list[str]] = defaultdict(list)

    def resolve_entities(self, *, query: str, filters: dict[str, object]) -> list[str]:
        tokens = set(query.lower().split())
        out: list[str] = []
        for uri, node in self._nodes.items():
            name_tokens = set(node.name.lower().split())
            if tokens & name_tokens:
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
        allowed = set(edge_types)
        visited = set(seed_uris)
        frontier = list(seed_uris)
        out_edges: list[GraphEdge] = []

        for _ in range(depth):
            next_frontier: list[str] = []
            for edge in self._edges:
                if allowed and edge.rel not in allowed:
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
        reasons = []
        if uri in self._nodes:
            reasons.append(f"uri {uri} exists in graph")
        linked = self._mentions.get(uri, [])
        if linked:
            reasons.append(f"linked entities: {', '.join(linked[:5])}")
        return reasons

    def upsert_mentions(self, *, chunk_uri: str, entity_uris: list[str], workspace_id: str) -> None:
        for entity_uri in entity_uris:
            if entity_uri not in self._nodes:
                self._nodes[entity_uri] = GraphNode(uri=entity_uri, type="Entity", name=entity_uri.split("/")[-1])
            if chunk_uri not in self._nodes:
                self._nodes[chunk_uri] = GraphNode(uri=chunk_uri, type="Chunk", name=chunk_uri.split("/")[-1])
            self._edges.append(GraphEdge(src=chunk_uri, rel="MENTIONS", dst=entity_uri))
            self._mentions[chunk_uri].append(entity_uri)

    def upsert_memory_links(self, *, memory_uri: str, entity_uris: list[str], workspace_id: str) -> None:
        if memory_uri not in self._nodes:
            self._nodes[memory_uri] = GraphNode(uri=memory_uri, type="Memory", name=memory_uri.split("/")[-1])
        for entity_uri in entity_uris:
            if entity_uri not in self._nodes:
                self._nodes[entity_uri] = GraphNode(uri=entity_uri, type="Entity", name=entity_uri.split("/")[-1])
            self._edges.append(GraphEdge(src=memory_uri, rel="MEMORY_REFERS_TO", dst=entity_uri))

    def delete_memory_nodes(self, *, memory_uris: list[str], filters: dict[str, object]) -> int:
        before = len(self._edges)
        memory_set = set(memory_uris)
        self._nodes = {k: v for k, v in self._nodes.items() if k not in memory_set}
        self._edges = [e for e in self._edges if e.src not in memory_set and e.dst not in memory_set]
        return before - len(self._edges)
