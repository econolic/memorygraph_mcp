from __future__ import annotations

from neo4j import GraphDatabase, RoutingControl

from kb_mcp.retrieval.models import GraphEdge, GraphNode


class Neo4jGraphStore:
    def __init__(self, *, uri: str, user: str, password: str, database: str) -> None:
        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        self._database = database

    def close(self) -> None:
        self._driver.close()

    def resolve_entities(self, *, query: str, filters: dict[str, object]) -> list[str]:
        workspace_id = str(filters.get("workspace_id", ""))
        records, _, _ = self._driver.execute_query(
            "MATCH (e:Entity {workspace_id: $workspace_id}) "
            "WHERE toLower(coalesce(e.name, '')) CONTAINS toLower($q) "
            "OR toLower(coalesce(e.canonical_key, '')) CONTAINS toLower($q) "
            "OR any(alias IN coalesce(e.aliases, []) WHERE toLower(alias) CONTAINS toLower($q)) "
            "RETURN e.uri AS uri LIMIT 20",
            parameters_={"workspace_id": workspace_id, "q": query},
            database_=self._database,
            routing_=RoutingControl.READ,
        )
        return [str(r["uri"]) for r in records]

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
        bounded_depth = max(1, min(depth, 4))

        node_query = (
            f"MATCH p=(a)-[*1..{bounded_depth}]-(b) "
            "WHERE a.uri IN $seed_uris "
            "AND a.workspace_id = $workspace_id "
            "AND b.workspace_id = $workspace_id "
            "UNWIND nodes(p) AS n "
            "RETURN DISTINCT n.uri AS uri, labels(n) AS labels, coalesce(n.name, n.uri) AS name, properties(n) AS props "
            "LIMIT $max_nodes"
        )
        edge_query = (
            f"MATCH p=(a)-[*1..{bounded_depth}]-(b) "
            "WHERE a.uri IN $seed_uris "
            "AND a.workspace_id = $workspace_id "
            "AND b.workspace_id = $workspace_id "
            "UNWIND relationships(p) AS rel "
            "WITH rel WHERE size($edge_types) = 0 OR type(rel) IN $edge_types "
            "RETURN DISTINCT startNode(rel).uri AS src, type(rel) AS rel_type, endNode(rel).uri AS dst "
            "LIMIT $max_nodes"
        )

        node_records, _, _ = self._driver.execute_query(
            node_query,
            parameters_={
                "seed_uris": seed_uris,
                "workspace_id": workspace_id,
                "max_nodes": max_nodes,
            },
            database_=self._database,
            routing_=RoutingControl.READ,
        )
        edge_records, _, _ = self._driver.execute_query(
            edge_query,
            parameters_={
                "seed_uris": seed_uris,
                "workspace_id": workspace_id,
                "max_nodes": max_nodes,
                "edge_types": edge_types,
            },
            database_=self._database,
            routing_=RoutingControl.READ,
        )

        nodes_by_uri: dict[str, GraphNode] = {}
        edges: list[GraphEdge] = []

        for record in node_records:
            uri = str(record["uri"])
            labels = record["labels"]
            node_type = "Entity"
            if isinstance(labels, list) and labels:
                node_type = str(labels[0])
            properties = record["props"] if isinstance(record["props"], dict) else {}
            nodes_by_uri[uri] = GraphNode(
                uri=uri,
                type=node_type,
                name=str(record["name"]),
                properties=properties,
            )

        for record in edge_records:
            src = str(record["src"])
            dst = str(record["dst"])
            rel_type = str(record["rel_type"])
            if not src or not dst:
                continue
            edges.append(GraphEdge(src=src, rel=rel_type, dst=dst))
        return list(nodes_by_uri.values()), edges

    def explain_uri(self, *, uri: str, filters: dict[str, object]) -> list[str]:
        workspace_id = str(filters.get("workspace_id", ""))
        records, _, _ = self._driver.execute_query(
            "MATCH (n {uri: $uri, workspace_id: $workspace_id})-[r]-(m) "
            "RETURN type(r) AS rel, m.uri AS uri LIMIT 20",
            parameters_={"uri": uri, "workspace_id": workspace_id},
            database_=self._database,
            routing_=RoutingControl.READ,
        )
        return [f"{uri} -[{r['rel']}]- {r['uri']}" for r in records]

    def upsert_mentions(
        self,
        *,
        doc_uri: str,
        chunk_uri: str,
        entity_uris: list[str],
        entity_names: dict[str, str],
        workspace_id: str,
    ) -> None:
        entities = []
        for entity_uri in entity_uris:
            canonical = entity_uri.split("kb://entity/")[-1]
            name = entity_names.get(entity_uri, canonical)
            entities.append(
                {
                    "uri": entity_uri,
                    "name": name,
                    "canonical_key": canonical,
                    "aliases": [name],
                }
            )

        self._driver.execute_query(
            "MERGE (d:Document {uri: $doc_uri, workspace_id: $workspace_id}) "
            "MERGE (c:Chunk {uri: $chunk_uri, workspace_id: $workspace_id}) "
            "ON CREATE SET c.name = $chunk_name "
            "MERGE (d)-[:CONTAINS]->(c) "
            "WITH d, c "
            "UNWIND $entities AS ent "
            "MERGE (e:Entity {uri: ent.uri, workspace_id: $workspace_id}) "
            "SET e.name = ent.name, e.canonical_key = ent.canonical_key, e.aliases = ent.aliases "
            "MERGE (c)-[:MENTIONS]->(e) "
            "MERGE (e)-[:DOCUMENTED_IN]->(d)",
            parameters_={
                "doc_uri": doc_uri,
                "chunk_uri": chunk_uri,
                "workspace_id": workspace_id,
                "entities": entities,
                "chunk_name": chunk_uri.split("/")[-1],
            },
            database_=self._database,
        )

    def upsert_memory_links(self, *, memory_uri: str, entity_uris: list[str], workspace_id: str) -> None:
        self._driver.execute_query(
            "MERGE (m:Memory {uri: $memory_uri, workspace_id: $workspace_id}) "
            "WITH m "
            "UNWIND $entity_uris AS euri "
            "MERGE (e:Entity {uri: euri, workspace_id: $workspace_id}) "
            "SET e.canonical_key = coalesce(e.canonical_key, split(euri, 'kb://entity/')[1]) "
            "MERGE (m)-[:MEMORY_REFERS_TO]->(e)",
            parameters_={"memory_uri": memory_uri, "entity_uris": entity_uris, "workspace_id": workspace_id},
            database_=self._database,
        )

    def delete_memory_nodes(self, *, memory_uris: list[str], filters: dict[str, object]) -> int:
        workspace_id = str(filters.get("workspace_id", ""))
        summary = self._driver.execute_query(
            "MATCH (m:Memory) WHERE m.uri IN $memory_uris AND m.workspace_id = $workspace_id "
            "DETACH DELETE m",
            parameters_={"memory_uris": memory_uris, "workspace_id": workspace_id},
            database_=self._database,
        )[1]
        return int(summary.counters.nodes_deleted)

    def delete_chunks(self, *, chunk_uris: list[str], filters: dict[str, object]) -> int:
        workspace_id = str(filters.get("workspace_id", ""))
        summary = self._driver.execute_query(
            "MATCH (c:Chunk) WHERE c.uri IN $chunk_uris AND c.workspace_id = $workspace_id "
            "DETACH DELETE c",
            parameters_={"chunk_uris": chunk_uris, "workspace_id": workspace_id},
            database_=self._database,
        )[1]
        return int(summary.counters.nodes_deleted)

    def upsert_entity_relations(self, *, relations: list[dict[str, str]], workspace_id: str) -> None:
        allowed = {"DEPENDS_ON", "CALLS", "OWNS", "IMPLEMENTS", "AFFECTS"}
        for relation in relations:
            src = relation.get("src", "")
            dst = relation.get("dst", "")
            rel_type = relation.get("rel", "")
            if not src or not dst or rel_type not in allowed:
                continue
            self._driver.execute_query(
                f"MERGE (a:Entity {{uri: $src, workspace_id: $workspace_id}}) "
                f"MERGE (b:Entity {{uri: $dst, workspace_id: $workspace_id}}) "
                f"MERGE (a)-[:{rel_type}]->(b)",
                parameters_={"src": src, "dst": dst, "workspace_id": workspace_id},
                database_=self._database,
            )
