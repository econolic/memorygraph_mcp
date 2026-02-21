from __future__ import annotations

import re


def _char_chunks(
    text: str,
    *,
    max_chars: int,
    overlap: int,
    base_offset: int = 0,
) -> list[dict[str, object]]:
    if not text:
        return []
    chunks: list[dict[str, object]] = []
    start = 0
    length = len(text)
    while start < length:
        end = min(length, start + max_chars)
        chunk = text[start:end]
        chunks.append(
            {
                "text": chunk,
                "span": {
                    "start": start + base_offset,
                    "end": end + base_offset,
                },
            }
        )
        if end == length:
            break
        start = max(0, end - overlap)
    return chunks


def _sentence_chunks(text: str, *, max_chars: int, overlap: int) -> list[dict[str, object]]:
    if not text:
        return []

    # Keep sentence boundaries when possible, fallback to char window for long fragments.
    sentence_spans = [(m.start(), m.end()) for m in re.finditer(r".+?(?:[.!?](?:\s+|$)|\n+|$)", text, re.DOTALL)]
    if not sentence_spans:
        return _char_chunks(text, max_chars=max_chars, overlap=overlap)

    chunks: list[dict[str, object]] = []
    current_start = sentence_spans[0][0]
    current_end = sentence_spans[0][1]
    for start, end in sentence_spans[1:]:
        proposed_len = end - current_start
        if proposed_len <= max_chars:
            current_end = end
            continue

        block = text[current_start:current_end]
        if (current_end - current_start) > max_chars:
            chunks.extend(_char_chunks(block, max_chars=max_chars, overlap=overlap, base_offset=current_start))
        else:
            chunks.append({"text": block, "span": {"start": current_start, "end": current_end}})
        current_start = start
        current_end = end

    tail_block = text[current_start:current_end]
    if tail_block:
        if (current_end - current_start) > max_chars:
            chunks.extend(_char_chunks(tail_block, max_chars=max_chars, overlap=overlap, base_offset=current_start))
        else:
            chunks.append({"text": tail_block, "span": {"start": current_start, "end": current_end}})
    return chunks


def chunk_text(
    text: str,
    *,
    max_chars: int = 800,
    overlap: int = 120,
    mode: str = "char",
) -> list[dict[str, object]]:
    if mode == "sentence":
        return _sentence_chunks(text, max_chars=max_chars, overlap=overlap)
    return _char_chunks(text, max_chars=max_chars, overlap=overlap)
