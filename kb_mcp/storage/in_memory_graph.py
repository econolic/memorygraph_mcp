from __future__ import annotations

from collections import defaultdict

from kb_mcp.retrieval.models import GraphEdge, GraphNode


class InMemoryGraphStore:
    def __init__(self) -> None:
        self._nodes: dict[str, GraphNode] = {}
        self._edges: list[GraphEdge] = []
        self._mentions: dict[str, list[str]] = defaultdict(list)

    @staticmethod
    def _acl_subjects(filters: dict[str, object]) -> set[str]:
        subjects: set[str] = set()
        acl_subject = str(filters.get("acl_subject", "")).strip()
        if acl_subject:
            subjects.add(acl_subject)
        roles_raw = filters.get("acl_roles", [])
        if isinstance(roles_raw, list):
            for role in roles_raw:
                role_value = str(role).strip()
                if role_value:
                    subjects.add(f"role:{role_value}")
        return subjects

    @staticmethod
    def _merge_acl(existing: object, incoming: list[str]) -> list[str]:
        values: list[str] = []
        if isinstance(existing, list):
            for item in existing:
                item_value = str(item).strip()
                if item_value and item_value not in values:
                    values.append(item_value)
        for item in incoming:
            item_value = str(item).strip()
            if item_value and item_value not in values:
                values.append(item_value)
        return values

    def _workspace_allows(self, uri: str, workspace_id: str) -> bool:
        node = self._nodes.get(uri)
        if node is None:
            return False
        return str(node.properties.get("workspace_id", "")) == workspace_id

    def _acl_allows(self, uri: str, filters: dict[str, object]) -> bool:
        node = self._nodes.get(uri)
        if node is None:
            return False
        if not bool(filters.get("graph_enforce_object_acl", True)):
            return True
        acl_allow = node.properties.get("acl_allow", [])
        if not isinstance(acl_allow, list) or not acl_allow:
            return False
        return bool(set(str(v) for v in acl_allow) & self._acl_subjects(filters))

    def _node_visible(self, uri: str, *, workspace_id: str, filters: dict[str, object]) -> bool:
        return self._workspace_allows(uri, workspace_id) and self._acl_allows(uri, filters)

    def resolve_entities(self, *, query: str, filters: dict[str, object]) -> list[str]:
        tokens = set(query.lower().split())
        workspace_id = str(filters.get("workspace_id", ""))
        out: list[str] = []
        for uri, node in self._nodes.items():
            if node.type != "Entity":
                continue
            if workspace_id and not self._node_visible(uri, workspace_id=workspace_id, filters=filters):
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
        allowed = set(edge_types) if edge_types else {
            "CONTAINS",
            "MENTIONS",
            "DOCUMENTED_IN",
            "DEPENDS_ON",
            "CALLS",
            "OWNS",
            "IMPLEMENTS",
            "AFFECTS",
        }
        visited = {
            uri
            for uri in seed_uris
            if self._node_visible(uri, workspace_id=workspace_id, filters=filters)
        }
        frontier = list(visited)
        out_edges: list[GraphEdge] = []

        for _ in range(depth):
            next_frontier: list[str] = []
            for edge in self._edges:
                if allowed and edge.rel not in allowed:
                    continue
                if not self._node_visible(edge.src, workspace_id=workspace_id, filters=filters):
                    continue
                if not self._node_visible(edge.dst, workspace_id=workspace_id, filters=filters):
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
        if node is not None and self._node_visible(uri, workspace_id=workspace_id, filters=filters):
            reasons.append(f"uri {uri} exists in graph")
        linked = [
            linked_uri
            for linked_uri in self._mentions.get(uri, [])
            if self._node_visible(linked_uri, workspace_id=workspace_id, filters=filters)
        ]
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
        acl_allow: list[str],
    ) -> None:
        if doc_uri not in self._nodes:
            self._nodes[doc_uri] = GraphNode(
                uri=doc_uri,
                type="Document",
                name=doc_uri.split("/")[-1],
                properties={"workspace_id": workspace_id, "acl_allow": list(acl_allow)},
            )
        else:
            doc = self._nodes[doc_uri]
            props = dict(doc.properties)
            props["workspace_id"] = workspace_id
            props["acl_allow"] = self._merge_acl(props.get("acl_allow", []), acl_allow)
            self._nodes[doc_uri] = GraphNode(uri=doc.uri, type=doc.type, name=doc.name, properties=props)
        if chunk_uri not in self._nodes:
            self._nodes[chunk_uri] = GraphNode(
                uri=chunk_uri,
                type="Chunk",
                name=chunk_uri.split("/")[-1],
                properties={"workspace_id": workspace_id, "acl_allow": list(acl_allow)},
            )
        else:
            chunk = self._nodes[chunk_uri]
            props = dict(chunk.properties)
            props["workspace_id"] = workspace_id
            props["acl_allow"] = self._merge_acl(props.get("acl_allow", []), acl_allow)
            self._nodes[chunk_uri] = GraphNode(uri=chunk.uri, type=chunk.type, name=chunk.name, properties=props)
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
                        "acl_allow": list(acl_allow),
                        "canonical_key": canonical,
                        "aliases": [entity_names.get(entity_uri, canonical)],
                    },
                )
            else:
                entity = self._nodes[entity_uri]
                props = dict(entity.properties)
                props["workspace_id"] = workspace_id
                props["acl_allow"] = self._merge_acl(props.get("acl_allow", []), acl_allow)
                self._nodes[entity_uri] = GraphNode(
                    uri=entity.uri,
                    type=entity.type,
                    name=entity.name,
                    properties=props,
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

    def upsert_entity_relations(
        self,
        *,
        relations: list[dict[str, str]],
        workspace_id: str,
        acl_allow: list[str],
    ) -> None:
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
                    properties={"workspace_id": workspace_id, "acl_allow": list(acl_allow)},
                )
            else:
                node = self._nodes[src]
                props = dict(node.properties)
                props["workspace_id"] = workspace_id
                props["acl_allow"] = self._merge_acl(props.get("acl_allow", []), acl_allow)
                self._nodes[src] = GraphNode(uri=node.uri, type=node.type, name=node.name, properties=props)
            if dst not in self._nodes:
                self._nodes[dst] = GraphNode(
                    uri=dst,
                    type="Entity",
                    name=dst.split("/")[-1],
                    properties={"workspace_id": workspace_id, "acl_allow": list(acl_allow)},
                )
            else:
                node = self._nodes[dst]
                props = dict(node.properties)
                props["workspace_id"] = workspace_id
                props["acl_allow"] = self._merge_acl(props.get("acl_allow", []), acl_allow)
                self._nodes[dst] = GraphNode(uri=node.uri, type=node.type, name=node.name, properties=props)
            self._edges.append(GraphEdge(src=src, rel=rel_type, dst=dst))
