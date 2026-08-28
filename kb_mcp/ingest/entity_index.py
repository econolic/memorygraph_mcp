from __future__ import annotations

from typing import Any, Iterable


def entity_vector_record(entity: dict[str, Any]) -> dict[str, object] | None:
    entity_id = str(entity.get("uri", "")).strip()
    name = str(entity.get("name", "")).strip()
    aliases_raw = entity.get("aliases", [])
    aliases = (
        [str(alias).strip() for alias in aliases_raw if str(alias).strip()]
        if isinstance(aliases_raw, list)
        else []
    )
    terms: list[str] = []
    for term in [name, *aliases]:
        if term and term not in terms:
            terms.append(term)
    if not entity_id or not terms:
        return None

    payload = dict(entity)
    payload["uri"] = entity_id
    payload["name"] = name or terms[0]
    payload["aliases"] = aliases
    return {
        "entity_id": entity_id,
        "text": " ".join(terms),
        "payload": payload,
    }


def entity_vector_records(entities: Iterable[dict[str, Any]]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for entity in entities:
        record = entity_vector_record(entity)
        if record is not None:
            records.append(record)
    return records
