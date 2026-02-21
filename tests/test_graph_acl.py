from __future__ import annotations

from kb_mcp.storage.in_memory_graph import InMemoryGraphStore


def _seed_graph(graph: InMemoryGraphStore) -> None:
    graph.upsert_mentions(
        doc_uri="kb://doc/d1",
        chunk_uri="kb://chunk/c1",
        entity_uris=["kb://entity/e1"],
        entity_names={"kb://entity/e1": "ServiceU1"},
        workspace_id="w1",
        acl_allow=["u1"],
    )
    graph.upsert_mentions(
        doc_uri="kb://doc/d2",
        chunk_uri="kb://chunk/c2",
        entity_uris=["kb://entity/e2"],
        entity_names={"kb://entity/e2": "ServiceU2"},
        workspace_id="w1",
        acl_allow=["u2"],
    )


def test_graph_expand_enforces_object_acl() -> None:
    graph = InMemoryGraphStore()
    _seed_graph(graph)

    nodes, edges = graph.expand(
        seed_uris=["kb://entity/e1", "kb://entity/e2"],
        depth=2,
        edge_types=[],
        max_nodes=200,
        filters={"workspace_id": "w1", "acl_subject": "u1", "graph_enforce_object_acl": True},
    )
    uris = {node.uri for node in nodes}
    assert "kb://entity/e1" in uris
    assert "kb://chunk/c1" in uris
    assert "kb://doc/d1" in uris
    assert "kb://entity/e2" not in uris
    assert "kb://chunk/c2" not in uris
    assert "kb://doc/d2" not in uris
    assert all("c2" not in edge.src and "c2" not in edge.dst for edge in edges)


def test_graph_explain_hides_foreign_nodes() -> None:
    graph = InMemoryGraphStore()
    _seed_graph(graph)

    owner_reasons = graph.explain_uri(
        uri="kb://chunk/c1",
        filters={"workspace_id": "w1", "acl_subject": "u1", "graph_enforce_object_acl": True},
    )
    foreign_reasons = graph.explain_uri(
        uri="kb://chunk/c2",
        filters={"workspace_id": "w1", "acl_subject": "u1", "graph_enforce_object_acl": True},
    )
    assert owner_reasons
    assert foreign_reasons == []


def test_graph_acl_can_be_disabled_by_flag() -> None:
    graph = InMemoryGraphStore()
    _seed_graph(graph)

    nodes, _edges = graph.expand(
        seed_uris=["kb://entity/e1", "kb://entity/e2"],
        depth=2,
        edge_types=[],
        max_nodes=200,
        filters={"workspace_id": "w1", "graph_enforce_object_acl": False},
    )
    uris = {node.uri for node in nodes}
    assert "kb://entity/e1" in uris
    assert "kb://entity/e2" in uris
