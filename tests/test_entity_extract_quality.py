from __future__ import annotations

from kb_mcp.ingest.entity_extract import (
    EntityExtractionConfig,
    extract_entities,
    extract_entity_aliases,
    extract_entity_relations,
)


def test_extract_entities_applies_stopwords_and_dedup() -> None:
    cfg = EntityExtractionConfig(
        stopwords=("service", "return"),
        min_symbol_len=3,
    )
    text = "Service ServiceA servicea return ServiceA"
    entities = extract_entities(text, cfg=cfg)
    assert entities == ["kb://entity/symbol:servicea"]


def test_extract_entity_aliases_keeps_variants() -> None:
    text = "ServiceA depends on ServiceB. serviceA depends on ServiceB."
    aliases = extract_entity_aliases(text)
    assert "kb://entity/symbol:servicea" in aliases
    assert "ServiceA" in aliases["kb://entity/symbol:servicea"]
    assert "serviceA" in aliases["kb://entity/symbol:servicea"]


def test_extract_relations_picks_entities_near_trigger() -> None:
    text = "Alpha Beta Gamma ServiceA depends on ServiceB and ServiceC."
    entities = extract_entities(text)
    rels = extract_entity_relations(text, entities)
    assert {"src": "kb://entity/symbol:servicea", "dst": "kb://entity/symbol:serviceb", "rel": "DEPENDS_ON"} in rels


def test_extract_relations_multiple_triggers() -> None:
    text = "ServiceA depends on ServiceB. ServiceC calls ServiceD."
    entities = extract_entities(text)
    rels = extract_entity_relations(text, entities)
    assert {"src": "kb://entity/symbol:servicea", "dst": "kb://entity/symbol:serviceb", "rel": "DEPENDS_ON"} in rels
    assert {"src": "kb://entity/symbol:servicec", "dst": "kb://entity/symbol:serviced", "rel": "CALLS"} in rels
