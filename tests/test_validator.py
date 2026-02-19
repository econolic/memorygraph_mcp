from __future__ import annotations

from kb_mcp.memory.validator import MemoryFactValidator


def test_validator_rejects_fact_without_citation() -> None:
    v = MemoryFactValidator(confidence_threshold=0.75)
    result = v.validate(memory_type="fact", text="lagerid: links", citations=[], confidence=0.9)
    assert result.ok is False
    assert "missing_citations" in result.reasons


def test_validator_accepts_good_fact() -> None:
    v = MemoryFactValidator(confidence_threshold=0.75)
    result = v.validate(
        memory_type="fact",
        text="lagerid: used in plan=fact reconciliation",
        citations=[{"uri": "kb://doc/doc1", "chunk_uri": "kb://chunk/ch1", "span": {"start": 1, "end": 2}}],
        confidence=0.9,
    )
    assert result.ok is True
