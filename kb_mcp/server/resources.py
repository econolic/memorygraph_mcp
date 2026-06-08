from __future__ import annotations

from typing import Any
from mcp.server.fastmcp import FastMCP
from kb_mcp.server.helpers import FastContext

from kb_mcp.retrieval.router import POLICY_VERSION
from kb_mcp.server.helpers import (
    request_from_ctx,
    resource_allowed,
    contract_ok,
    contract_error,
)

def register_resources(mcp: FastMCP, deps: Any) -> None:
    @mcp.resource("kb://doc/{doc_id}")
    def resource_doc(doc_id: str, ctx: FastContext | None = None) -> dict[str, Any]:
        uri = f"kb://doc/{doc_id}"
        doc = deps.metadata.get_doc(uri)
        if doc is None:
            return contract_error(
                uri=uri,
                legacy_error="not_found",
                error_code="NOT_FOUND",
                detail="Document resource was not found.",
            )
        auth = deps.auth.resolve_identity(
            request=request_from_ctx(ctx),
            payload_acl=None,
            allow_legacy_payload=False,
        )
        if not resource_allowed(deps=deps, auth_ctx=auth.ctx, data=doc):
            return contract_error(
                uri=uri,
                legacy_error="forbidden",
                error_code="PERMISSION_DENIED",
                detail="Bearer identity cannot read this document resource.",
            )
        out = dict(doc)
        if "text" in out:
            out["text"] = deps.redact.redact(str(out["text"]))
        return contract_ok(out)

    @mcp.resource("kb://chunk/{chunk_id}")
    def resource_chunk(chunk_id: str, ctx: FastContext | None = None) -> dict[str, Any]:
        uri = f"kb://chunk/{chunk_id}"
        chunk = deps.metadata.get_chunk(uri)
        if chunk is None:
            return contract_error(
                uri=uri,
                legacy_error="not_found",
                error_code="NOT_FOUND",
                detail="Chunk resource was not found.",
            )
        auth = deps.auth.resolve_identity(
            request=request_from_ctx(ctx),
            payload_acl=None,
            allow_legacy_payload=False,
        )
        if not resource_allowed(deps=deps, auth_ctx=auth.ctx, data=chunk):
            return contract_error(
                uri=uri,
                legacy_error="forbidden",
                error_code="PERMISSION_DENIED",
                detail="Bearer identity cannot read this chunk resource.",
            )
        out = dict(chunk)
        out["text"] = deps.redact.redact(str(out.get("text", "")))
        return contract_ok(out)

    @mcp.resource("kb://entity/{entity_id}")
    def resource_entity(entity_id: str, ctx: FastContext | None = None) -> dict[str, Any]:
        uri = f"kb://entity/{entity_id}"
        entity = deps.metadata.get_entity(uri)
        if entity is None:
            return contract_ok({"uri": uri, "type": "Entity", "name": entity_id, "links": []})
        auth = deps.auth.resolve_identity(
            request=request_from_ctx(ctx),
            payload_acl=None,
            allow_legacy_payload=False,
        )
        if not resource_allowed(deps=deps, auth_ctx=auth.ctx, data=entity):
            return contract_error(
                uri=uri,
                legacy_error="forbidden",
                error_code="PERMISSION_DENIED",
                detail="Bearer identity cannot read this entity resource.",
            )
        return contract_ok(entity)

    @mcp.resource("kb://memory/{memory_id}")
    def resource_memory(memory_id: str, ctx: FastContext | None = None) -> dict[str, Any]:
        uri = f"kb://memory/{memory_id}"
        memory = deps.metadata.get_memory(uri)
        if memory is None:
            return contract_error(
                uri=uri,
                legacy_error="not_found",
                error_code="NOT_FOUND",
                detail="Memory resource was not found.",
            )
        auth = deps.auth.resolve_identity(
            request=request_from_ctx(ctx),
            payload_acl=None,
            allow_legacy_payload=False,
        )
        if not resource_allowed(deps=deps, auth_ctx=auth.ctx, data=memory):
            return contract_error(
                uri=uri,
                legacy_error="forbidden",
                error_code="PERMISSION_DENIED",
                detail="Bearer identity cannot read this memory resource.",
            )
        out = dict(memory)
        out["text"] = deps.redact.redact(str(out.get("text", "")))
        return contract_ok(out)

    @mcp.resource("kb://policy/tool-selection")
    def resource_tool_selection_policy() -> dict[str, Any]:
        return contract_ok({
            "version": POLICY_VERSION,
            "intent_catalog": [
                "fact_lookup",
                "relation_impact",
                "explainability",
                "memory_context",
                "memory_delete",
            ],
            "priority_tools": [
                "kb_route",
                "kb_memory_search",
                "kb_search",
                "kb_graph_expand",
                "kb_explain",
            ],
            "router_tool": "kb_route",
            "memory_write_constraints": {
                "tool": "kb_memory_upsert",
                "requires_citations": True,
                "requires_confidence_threshold": True,
            },
            "fallback_policy": "When graph backend is unavailable, return vector-only evidence with explicit limitation.",
        })
