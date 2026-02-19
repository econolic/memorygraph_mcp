from __future__ import annotations

from dataclasses import dataclass, field

from kb_mcp.storage.metadata_store import MetadataStore


@dataclass(frozen=True)
class EvidenceItem:
    uri: str
    title: str
    snippet: str
    score: float
    score_breakdown: dict[str, float] = field(default_factory=dict)
    citations: list[dict[str, object]] = field(default_factory=list)
    entities: list[dict[str, str]] = field(default_factory=list)


class EvidenceBuilder:
    def __init__(self, metadata: MetadataStore) -> None:
        self._metadata = metadata

    def build(self, *, uri: str, score: float, breakdown: dict[str, float]) -> EvidenceItem:
        chunk = self._metadata.get_chunk(uri)
        if chunk is None:
            return EvidenceItem(
                uri=uri,
                title="Unknown",
                snippet="",
                score=score,
                score_breakdown=breakdown,
            )

        doc = self._metadata.get_doc(chunk["doc_uri"])
        title = str(doc["title"]) if doc else "Unknown"
        snippet = str(chunk["text"])
        span = chunk.get("span", {"start": 0, "end": len(snippet)})
        citations = [
            {
                "uri": chunk["doc_uri"],
                "chunk_uri": uri,
                "span": span,
            }
        ]
        entities = [
            {"uri": str(entity_uri), "type": "Entity", "name": str(entity_uri).split("/")[-1]}
            for entity_uri in chunk.get("entity_uris", [])
        ]

        return EvidenceItem(
            uri=uri,
            title=title,
            snippet=snippet,
            score=score,
            score_breakdown=breakdown,
            citations=citations,
            entities=entities,
        )
