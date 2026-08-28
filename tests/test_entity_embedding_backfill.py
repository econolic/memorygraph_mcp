from __future__ import annotations

from kb_mcp.backfill_entity_embeddings import backfill_entity_embeddings
from kb_mcp.storage.in_memory_vector import InMemoryVectorStore
from kb_mcp.storage.metadata_store import MetadataStore


class _TrackingVectorStore(InMemoryVectorStore):
    def __init__(self) -> None:
        super().__init__()
        self.batch_sizes: list[int] = []

    def upsert_entities(self, *, entities: list[dict[str, object]]) -> None:
        self.batch_sizes.append(len(entities))
        super().upsert_entities(entities=entities)


def test_backfill_entity_embeddings_is_batched_and_searchable() -> None:
    metadata = MetadataStore()
    for index in range(5):
        metadata.put_entity(
            f"kb://entity/{index}",
            {
                "uri": f"kb://entity/{index}",
                "workspace_id": "w1",
                "acl_allow": ["u1"],
                "name": f"Entity{index}",
                "aliases": [f"alias{index}"],
            },
        )
    metadata.put_entity(
        "kb://entity/other",
        {
            "uri": "kb://entity/other",
            "workspace_id": "w2",
            "acl_allow": ["u2"],
            "name": "Other",
        },
    )
    vector = _TrackingVectorStore()

    result = backfill_entity_embeddings(
        metadata=metadata,
        vector_store=vector,
        workspace_id="w1",
        batch_size=2,
    )

    assert result == {
        "workspace_id": "w1",
        "entities_seen": 5,
        "indexed": 5,
        "skipped": 0,
    }
    assert vector.batch_sizes == [2, 2, 1]
    hits = vector.search_entities(
        query="Entity3",
        top_k=5,
        filters={"workspace_id": "w1", "acl_subject": "u1"},
    )
    assert hits[0].item_id == "kb://entity/3"
