from __future__ import annotations

import re


_TABLE_RE = re.compile(r"\b([a-z_]+\.[a-z_]+)\b", re.IGNORECASE)
_SYMBOL_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]{2,})\b")
_CYR_RE = re.compile(r"\b([А-Яа-яЁё][А-Яа-яЁё0-9_\-]{2,})\b")


def _entity_uri(prefix: str, value: str) -> str:
    return f"kb://entity/{prefix}:{value}"


def extract_entities(text: str) -> list[str]:
    entities = set()
    for match in _TABLE_RE.findall(text):
        entities.add(_entity_uri("table", match.lower()))
    for match in _SYMBOL_RE.findall(text):
        entities.add(_entity_uri("symbol", match))
    for match in _CYR_RE.findall(text):
        entities.add(_entity_uri("term", match.lower()))
    return sorted(entities)


def entity_display_name(entity_uri: str) -> str:
    suffix = entity_uri.split("kb://entity/")[-1]
    if ":" in suffix:
        return suffix.split(":", 1)[1]
    return suffix


def extract_entity_relations(text: str, entity_uris: list[str]) -> list[dict[str, str]]:
    """Rule-based extraction for domain relations without LLM write-back."""
    if len(entity_uris) < 2:
        return []

    lower = text.lower()
    relation_type = ""
    if "depends on" in lower or "зависит от" in lower:
        relation_type = "DEPENDS_ON"
    elif "calls" in lower or "вызывает" in lower:
        relation_type = "CALLS"
    elif "owns" in lower or "владеет" in lower:
        relation_type = "OWNS"
    elif "implements" in lower or "реализует" in lower:
        relation_type = "IMPLEMENTS"
    elif "affects" in lower or "влияет на" in lower:
        relation_type = "AFFECTS"

    if not relation_type:
        return []

    src = entity_uris[0]
    dst = entity_uris[1]
    return [{"src": src, "dst": dst, "rel": relation_type}]
