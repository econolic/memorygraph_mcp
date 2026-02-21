from __future__ import annotations

from kb_mcp.storage.in_memory_vector import InMemoryVectorStore


def test_in_memory_search_filters_tags_sources_updated_after() -> None:
    store = InMemoryVectorStore()
    store.upsert_chunk(
        chunk_id="old_chunk",
        text="API contract old version",
        payload={
            "workspace_id": "w1",
            "acl_allow": ["u1"],
            "source": "doc_api_contract.md",
            "tags": ["ext:md", "api"],
            "updated_at": "2026-01-01T00:00:00+00:00",
        },
    )
    store.upsert_chunk(
        chunk_id="fresh_chunk",
        text="API contract fresh version",
        payload={
            "workspace_id": "w1",
            "acl_allow": ["u1"],
            "source": "doc_api_contract.md",
            "tags": ["ext:md", "api"],
            "updated_at": "2026-02-20T00:00:00+00:00",
        },
    )
    store.upsert_chunk(
        chunk_id="other_source",
        text="API contract fresh different source",
        payload={
            "workspace_id": "w1",
            "acl_allow": ["u1"],
            "source": "doc_other.md",
            "tags": ["ext:md", "api"],
            "updated_at": "2026-02-20T00:00:00+00:00",
        },
    )

    hits = store.search_chunks(
        query="API contract",
        top_k=10,
        filters={
            "workspace_id": "w1",
            "acl_subject": "u1",
            "tags": ["api"],
            "sources": ["doc_api_contract.md"],
            "updated_after": "2026-02-01T00:00:00Z",
        },
    )
    assert len(hits) == 1
    assert hits[0].item_id == "fresh_chunk"


def test_in_memory_updated_after_excludes_older_chunks() -> None:
    store = InMemoryVectorStore()
    store.upsert_chunk(
        chunk_id="c1",
        text="lagerid mapping",
        payload={
            "workspace_id": "w1",
            "acl_allow": ["u1"],
            "source": "doc_memory.md",
            "tags": ["ext:md"],
            "updated_at": "2026-01-01T00:00:00+00:00",
        },
    )
    hits = store.search_chunks(
        query="lagerid",
        top_k=10,
        filters={
            "workspace_id": "w1",
            "acl_subject": "u1",
            "updated_after": "2026-02-01T00:00:00+00:00",
        },
    )
    assert hits == []
