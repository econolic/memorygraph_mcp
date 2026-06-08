from __future__ import annotations

import re
import math
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from kb_mcp.ingest.embeddings import Embedder


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


def _semantic_chunks(
    text: str,
    *,
    max_chars: int,
    overlap: int,
    embedder: Embedder | None,
    similarity_threshold: float = 0.5,
) -> list[dict[str, object]]:
    if not text:
        return []
    if embedder is None:
        return _sentence_chunks(text, max_chars=max_chars, overlap=overlap)

    sentence_spans = [(m.start(), m.end()) for m in re.finditer(r".+?(?:[.!?](?:\s+|$)|\n+|$)", text, re.DOTALL)]
    if len(sentence_spans) <= 1:
        return _char_chunks(text, max_chars=max_chars, overlap=overlap)

    # Extract texts and get embeddings
    sentence_texts = [text[start:end] for start, end in sentence_spans]
    try:
        vectors = embedder.embed_texts(sentence_texts)
    except Exception:
        return _sentence_chunks(text, max_chars=max_chars, overlap=overlap)

    if len(vectors) != len(sentence_spans):
        return _sentence_chunks(text, max_chars=max_chars, overlap=overlap)

    # Calculate cosine similarity between adjacent sentence embeddings
    splits = [False] * (len(sentence_spans) - 1)
    for i in range(len(vectors) - 1):
        v1, v2 = vectors[i], vectors[i+1]
        dot = sum(a * b for a, b in zip(v1, v2))
        n1 = math.sqrt(sum(a * a for a in v1))
        n2 = math.sqrt(sum(b * b for b in v2))
        sim = dot / (n1 * n2) if n1 > 0 and n2 > 0 else 0.0
        if sim < similarity_threshold:
            splits[i] = True

    # Build initial chunks based on splits
    chunks: list[dict[str, object]] = []
    curr_start_idx = 0
    
    for i in range(len(splits)):
        if splits[i]:
            c_start = sentence_spans[curr_start_idx][0]
            c_end = sentence_spans[i][1]
            block = text[c_start:c_end]
            if len(block) > max_chars:
                chunks.extend(_char_chunks(block, max_chars=max_chars, overlap=overlap, base_offset=c_start))
            else:
                chunks.append({"text": block, "span": {"start": c_start, "end": c_end}})
            curr_start_idx = i + 1

    # Add final block
    c_start = sentence_spans[curr_start_idx][0]
    c_end = sentence_spans[-1][1]
    block = text[c_start:c_end]
    if len(block) > max_chars:
        chunks.extend(_char_chunks(block, max_chars=max_chars, overlap=overlap, base_offset=c_start))
    else:
        chunks.append({"text": block, "span": {"start": c_start, "end": c_end}})

    # Merge contiguous small chunks
    merged_chunks: list[dict[str, object]] = []
    if chunks:
        current = chunks[0]
        for next_chunk in chunks[1:]:
            current_span = cast("dict[str, int]", current["span"])
            next_span = cast("dict[str, int]", next_chunk["span"])
            if next_span["start"] == current_span["end"] and (next_span["end"] - current_span["start"]) <= max_chars:
                current = {
                    "text": text[current_span["start"]:next_span["end"]],
                    "span": {"start": current_span["start"], "end": next_span["end"]}
                }
            else:
                merged_chunks.append(current)
                current = next_chunk
        merged_chunks.append(current)
        return merged_chunks
    return chunks


def _code_chunks(
    text: str,
    *,
    max_chars: int,
    overlap: int,
    language: str = "python",
) -> list[dict[str, object]]:
    if not text:
        return []

    lines = text.splitlines(keepends=True)
    splits = [False] * len(lines)

    for idx, line in enumerate(lines):
        striped = line.lstrip()
        if language == "python":
            if (line.startswith("def ") or line.startswith("class ") or line.startswith("async def ")) and not line.startswith(" "):
                splits[idx] = True
        else:
            if idx > 0 and not lines[idx-1].strip() and striped:
                splits[idx] = True

    # Build line offsets
    curr_block_start = 0
    char_offset = 0
    line_offsets = []
    for line in lines:
        line_offsets.append(char_offset)
        char_offset += len(line)
    line_offsets.append(char_offset)

    chunks: list[dict[str, object]] = []

    for idx in range(len(lines)):
        if splits[idx] and idx > curr_block_start:
            b_start = line_offsets[curr_block_start]
            b_end = line_offsets[idx]
            block_text = text[b_start:b_end]
            if len(block_text) > max_chars:
                chunks.extend(_char_chunks(block_text, max_chars=max_chars, overlap=overlap, base_offset=b_start))
            else:
                chunks.append({"text": block_text, "span": {"start": b_start, "end": b_end}})
            curr_block_start = idx

    # Add final block
    b_start = line_offsets[curr_block_start]
    b_end = line_offsets[-1]
    block_text = text[b_start:b_end]
    if len(block_text) > max_chars:
        chunks.extend(_char_chunks(block_text, max_chars=max_chars, overlap=overlap, base_offset=b_start))
    elif block_text.strip():
        chunks.append({"text": block_text, "span": {"start": b_start, "end": b_end}})

    # Merge contiguous small chunks
    merged_chunks: list[dict[str, object]] = []
    if chunks:
        current = chunks[0]
        for next_chunk in chunks[1:]:
            current_span = cast("dict[str, int]", current["span"])
            next_span = cast("dict[str, int]", next_chunk["span"])
            if next_span["start"] == current_span["end"] and (next_span["end"] - current_span["start"]) <= max_chars:
                current = {
                    "text": text[current_span["start"]:next_span["end"]],
                    "span": {"start": current_span["start"], "end": next_span["end"]}
                }
            else:
                merged_chunks.append(current)
                current = next_chunk
        merged_chunks.append(current)
        return merged_chunks
    return chunks


def chunk_text(
    text: str,
    *,
    max_chars: int = 800,
    overlap: int = 120,
    mode: str = "char",
    embedder: Embedder | None = None,
    language: str | None = None,
    similarity_threshold: float = 0.5,
) -> list[dict[str, object]]:
    if mode == "semantic":
        return _semantic_chunks(text, max_chars=max_chars, overlap=overlap, embedder=embedder, similarity_threshold=similarity_threshold)
    if mode == "code":
        return _code_chunks(text, max_chars=max_chars, overlap=overlap, language=language or "python")
    if mode == "sentence":
        return _sentence_chunks(text, max_chars=max_chars, overlap=overlap)
    return _char_chunks(text, max_chars=max_chars, overlap=overlap)
