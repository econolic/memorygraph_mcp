from __future__ import annotations

from kb_mcp.memory.service import MemoryService
from kb_mcp.memory.validator import MemoryFactValidator
from kb_mcp.storage.in_memory_graph import InMemoryGraphStore
from kb_mcp.storage.in_memory_vector import InMemoryVectorStore
from kb_mcp.storage.metadata_store import MetadataStore


def test_memory_lifecycle() -> None:
    service = MemoryService(
        vector_store=InMemoryVectorStore(),
        graph_store=InMemoryGraphStore(),
        metadata=MetadataStore(),
        validator=MemoryFactValidator(confidence_threshold=0.5),
    )

    stored, report = service.upsert(
        workspace_id="w1",
        subject="u1",
        session_id="s1",
        items=[
            {
                "type": "fact",
                "text": "lagerid: appears in plan and writeoff",
                "citations": [{"chunk_uri": "kb://chunk/ch1", "span": {"start": 0, "end": 10}}],
                "confidence": 0.95,
                "entity_uris": ["kb://entity/term:lagerid"],
            }
        ],
    )

    assert len(stored) == 1
    assert report == {}

    hits = service.search(query="lagerid", workspace_id="w1", subject="u1", top_k=5)
    assert hits

    deleted = service.delete(workspace_id="w1", subject="u1", ids=stored, all_for_subject=False)
    assert deleted == 1
