from __future__ import annotations


def chunk_text(text: str, *, max_chars: int = 800, overlap: int = 120) -> list[dict[str, object]]:
    if not text:
        return []
    chunks: list[dict[str, object]] = []
    start = 0
    length = len(text)
    while start < length:
        end = min(length, start + max_chars)
        chunk = text[start:end]
        chunks.append({"text": chunk, "span": {"start": start, "end": end}})
        if end == length:
            break
        start = max(0, end - overlap)
    return chunks
