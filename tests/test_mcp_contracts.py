from __future__ import annotations

from kb_mcp.server.app import REGISTERED_PROMPTS, REGISTERED_RESOURCES, REGISTERED_TOOLS
from kb_mcp.server.schemas import KbHealthOutput, KbIngestOutput, KbSearchOutput


def test_registered_mcp_surface_includes_health_policy_and_prompts() -> None:
    assert "kb.health" in REGISTERED_TOOLS
    assert "kb.search" in REGISTERED_TOOLS
    assert "kb.ingest.filesystem" in REGISTERED_TOOLS
    assert "kb://policy/tool-selection" in REGISTERED_RESOURCES
    assert "kb.tool_selection_policy" in REGISTERED_PROMPTS


def test_additive_contract_fields_preserve_legacy_payload_fields() -> None:
    search = KbSearchOutput(query_id="q1", results=[])
    assert search.ok is True
    assert search.error_code is None
    assert search.error_detail is None
    assert search.meta == {}
    assert search.results == []

    ingest = KbIngestOutput(created=1, updated=2, skipped=3, dry_run=True)
    dumped = ingest.model_dump()
    assert dumped["created"] == 1
    assert dumped["updated"] == 2
    assert dumped["skipped"] == 3
    assert dumped["dry_run"] is True
    assert dumped["ok"] is True


def test_health_output_redacts_secret_values_by_design() -> None:
    health = KbHealthOutput(
        service_name="hybrid-kb-mcp",
        transport="mcp",
        auth_mode="strict",
        backends={"vector": "memory", "graph": "memory", "metadata": "memory"},
        tools=list(REGISTERED_TOOLS),
        resources=list(REGISTERED_RESOURCES),
        prompts=list(REGISTERED_PROMPTS),
        config={"http_host": "127.0.0.1", "ingest_allowed_roots": ["/repo"]},
    )
    dumped = health.model_dump()
    assert dumped["ok"] is True
    assert "jwt_secret" not in dumped["config"]
    assert "neo4j_password" not in dumped["config"]
