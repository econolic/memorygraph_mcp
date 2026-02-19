from __future__ import annotations

import re


_TABLE_RE = re.compile(r"\b([a-z_]+\.[a-z_]+)\b", re.IGNORECASE)
_SYMBOL_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]{2,})\b")
_CYR_RE = re.compile(r"\b([А-Яа-яЁё][А-Яа-яЁё0-9_\-]{2,})\b")


def extract_entities(text: str) -> list[str]:
    entities = set()
    for match in _TABLE_RE.findall(text):
        entities.add(f"kb://entity/table:{match.lower()}")
    for match in _SYMBOL_RE.findall(text):
        entities.add(f"kb://entity/symbol:{match}")
    for match in _CYR_RE.findall(text):
        entities.add(f"kb://entity/term:{match.lower()}")
    return sorted(entities)
