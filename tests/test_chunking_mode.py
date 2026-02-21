from __future__ import annotations

from kb_mcp.ingest.chunking import chunk_text


def test_sentence_chunking_preserves_sentence_boundaries() -> None:
    text = "Sentence one. Sentence two. Sentence three."
    chunks = chunk_text(text, max_chars=20, overlap=5, mode="sentence")
    assert chunks
    assert all(isinstance(chunk["text"], str) for chunk in chunks)
    assert all("span" in chunk for chunk in chunks)


def test_sentence_chunking_falls_back_for_long_sentence() -> None:
    text = "A" * 2000
    chunks = chunk_text(text, max_chars=400, overlap=50, mode="sentence")
    assert len(chunks) > 1
    starts = [int(chunk["span"]["start"]) for chunk in chunks if isinstance(chunk["span"], dict)]
    assert starts[0] == 0
