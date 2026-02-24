from __future__ import annotations

from dataclasses import dataclass, field

from neo4j import RoutingControl

from kb_mcp.storage.neo4j_store import Neo4jGraphStore


@dataclass
class _Counters:
    nodes_deleted: int = 1


@dataclass
class _Summary:
    counters: _Counters = field(default_factory=_Counters)


class _FakeNeo4jDriver:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def execute_query(self, query: str, **kwargs):  # noqa: ANN003
        self.calls.append({"query": query, "kwargs": kwargs})
        if "DETACH DELETE" in query:
            return ([], _Summary(), [])
        return ([], None, [])

    def close(self) -> None:
        return None


def test_neo4j_write_paths_use_explicit_database_and_write_routing(monkeypatch) -> None:
    fake_driver = _FakeNeo4jDriver()
    monkeypatch.setattr(
        "kb_mcp.storage.neo4j_store.GraphDatabase.driver",
        lambda uri, auth: fake_driver,  # noqa: ARG005
    )

    store = Neo4jGraphStore(uri="bolt://unused", user="neo4j", password="secret", database="neo4j")
    store.upsert_mentions(
        doc_uri="kb://doc/d1",
        chunk_uri="kb://chunk/c1",
        entity_uris=["kb://entity/symbol:svc_a"],
        entity_names={"kb://entity/symbol:svc_a": "ServiceA"},
        workspace_id="w1",
        acl_allow=["u1"],
    )
    store.upsert_memory_links(
        memory_uri="kb://memory/m1",
        entity_uris=["kb://entity/symbol:svc_a"],
        workspace_id="w1",
    )
    deleted = store.delete_memory_nodes(memory_uris=["kb://memory/m1"], filters={"workspace_id": "w1"})
    assert deleted == 1
    store.delete_chunks(chunk_uris=["kb://chunk/c1"], filters={"workspace_id": "w1"})
    store.upsert_entity_relations(
        relations=[{"src": "kb://entity/symbol:svc_a", "dst": "kb://entity/symbol:svc_b", "rel": "DEPENDS_ON"}],
        workspace_id="w1",
        acl_allow=["u1"],
    )

    assert fake_driver.calls
    for call in fake_driver.calls:
        kwargs = call["kwargs"]
        assert isinstance(kwargs, dict)
        assert kwargs.get("database_") == "neo4j"
        assert kwargs.get("routing_") == RoutingControl.WRITE
