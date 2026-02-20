from __future__ import annotations

from kb_mcp.storage.in_memory_vector import InMemoryVectorStore


def test_delete_memory_respects_workspace_and_subject_filters() -> None:
    store = InMemoryVectorStore()
    store.upsert_memory(
        memory_id="m1",
        text="note for u1",
        payload={"workspace_id": "w1", "acl_allow": ["u1"]},
    )
    store.upsert_memory(
        memory_id="m2",
        text="note for u2",
        payload={"workspace_id": "w2", "acl_allow": ["u2"]},
    )

    deleted = store.delete_memory(
        memory_ids=["m1", "m2"],
        filters={"workspace_id": "w1", "acl_subject": "u1"},
    )
    assert deleted == 1

    remaining = store.search_memory(query="note", top_k=10, filters={"workspace_id": "w2", "acl_subject": "u2"})
    assert len(remaining) == 1
    assert remaining[0].item_id == "m2"
