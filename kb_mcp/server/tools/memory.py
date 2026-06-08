from __future__ import annotations

from time import perf_counter
from typing import Any
from mcp.server.fastmcp import FastMCP
from kb_mcp.server.helpers import FastContext

from kb_mcp.server.schemas import (
    KbMemoryUpsertInput,
    KbMemoryUpsertOutput,
    KbMemorySearchInput,
    KbMemorySearchOutput,
    KbMemoryDeleteInput,
    KbMemoryDeleteOutput,
    MemoryHit,
)
from kb_mcp.server.helpers import (
    resolve_identity,
    audit_tool,
    legacy_acl,
    with_middlewares,
)

def register_memory_tools(mcp: FastMCP, deps: Any) -> None:
    @mcp.tool(name="kb_memory_upsert")
    @with_middlewares("kb_memory_upsert", deps)
    def kb_memory_upsert(payload: KbMemoryUpsertInput, ctx: FastContext | None = None) -> KbMemoryUpsertOutput:
        """Upsert (create or update) semantic memory items for a specific subject within a workspace."""
        t0 = perf_counter()
        auth = resolve_identity(deps, legacy_acl(workspace_id=payload.workspace_id, subject=payload.subject), ctx)
        stored_ids, report = deps.memory.upsert(
            workspace_id=auth.ctx.workspace_id,
            subject=auth.ctx.subject,
            session_id=payload.session_id,
            items=[item.model_dump() for item in payload.items],
            idempotency_key=payload.idempotency_key,
        )
        deps.metrics.inc("tool.kb_memory_upsert.calls")
        latency_ms = int((perf_counter() - t0) * 1000)
        deps.metrics.observe("tool.kb_memory_upsert.latency_ms", latency_ms)
        audit_tool(
            deps,
            auth=auth,
            tool="kb_memory_upsert",
            params=payload.model_dump(),
            result_count=len(stored_ids),
            latency_ms=latency_ms,
            acl_decision="applied",
        )
        return KbMemoryUpsertOutput(
            stored_ids=stored_ids,
            validation_report=report,
            meta={"latency_ms": latency_ms},
        )

    @mcp.tool(name="kb_memory_search")
    @with_middlewares("kb_memory_search", deps)
    def kb_memory_search(payload: KbMemorySearchInput, ctx: FastContext | None = None) -> KbMemorySearchOutput:
        """Search the semantic memory of a specific subject within a workspace."""
        t0 = perf_counter()
        auth = resolve_identity(deps, legacy_acl(workspace_id=payload.workspace_id, subject=payload.subject), ctx)
        hits = deps.memory.search(
            query=payload.query,
            workspace_id=auth.ctx.workspace_id,
            subject=auth.ctx.subject,
            top_k=payload.top_k,
        )
        deps.metrics.inc("tool.kb_memory_search.calls")
        latency_ms = int((perf_counter() - t0) * 1000)
        deps.metrics.observe("tool.kb_memory_search.latency_ms", latency_ms)
        audit_tool(
            deps,
            auth=auth,
            tool="kb_memory_search",
            params=payload.model_dump(),
            result_count=len(hits),
            latency_ms=latency_ms,
            acl_decision="applied",
        )
        return KbMemorySearchOutput(
            results=[
                MemoryHit(uri=hit.uri, score=hit.score, text=deps.redact.redact(hit.text), citations=hit.citations)
                for hit in hits
            ],
            meta={"latency_ms": latency_ms},
        )

    @mcp.tool(name="kb_memory_delete")
    @with_middlewares("kb_memory_delete", deps)
    def kb_memory_delete(payload: KbMemoryDeleteInput, ctx: FastContext | None = None) -> KbMemoryDeleteOutput:
        """Delete semantic memory items for a specific subject (requires multi-step confirmation token)."""
        t0 = perf_counter()
        auth = resolve_identity(deps, legacy_acl(workspace_id=payload.workspace_id, subject=payload.subject), ctx)

        # Destructive Confirmation flow
        if not payload.confirmation_token:
            if payload.all_for_subject:
                items = deps.metadata.list_memory(workspace_id=auth.ctx.workspace_id, subject=auth.ctx.subject)
            else:
                items = []
                for mid in payload.ids:
                    m_uri = f"kb://memory/{mid}"
                    m_item = deps.metadata.get_memory(m_uri)
                    if m_item and m_item.get("workspace_id") == auth.ctx.workspace_id and m_item.get("subject") == auth.ctx.subject:
                        items.append(m_item)

            preview_items = [{"id": str(item.get("uri", "")).split("/")[-1], "text": str(item.get("text", ""))[:100]} for item in items]
            gate_data = {
                "workspace_id": auth.ctx.workspace_id,
                "subject": auth.ctx.subject,
                "ids": payload.ids,
                "all_for_subject": payload.all_for_subject,
            }
            token = deps.confirmation.generate_token(gate_data)
            latency_ms = int((perf_counter() - t0) * 1000)
            return KbMemoryDeleteOutput(
                ok=False,
                error_code="BUSINESS_RULE_VIOLATION",
                error_detail="This operation is destructive and requires confirmation. Please call again with confirmation_token.",
                recoverable=True,
                next_action="provide confirmation_token",
                deleted_count=0,
                meta={
                    "confirmation_token": token,
                    "preview": {
                        "count": len(preview_items),
                        "items": preview_items,
                    },
                    "latency_ms": latency_ms,
                }
            )

        gate_data = deps.confirmation.validate_and_invalidate(payload.confirmation_token)
        if not gate_data:
            latency_ms = int((perf_counter() - t0) * 1000)
            return KbMemoryDeleteOutput(
                ok=False,
                error_code="VALIDATION_ERROR",
                error_detail="Invalid or expired confirmation token.",
                deleted_count=0,
                meta={"latency_ms": latency_ms}
            )

        deleted = deps.memory.delete(
            workspace_id=auth.ctx.workspace_id,
            subject=auth.ctx.subject,
            ids=gate_data["ids"],
            all_for_subject=gate_data["all_for_subject"],
        )
        deps.metrics.inc("tool.kb_memory_delete.calls")
        latency_ms = int((perf_counter() - t0) * 1000)
        deps.metrics.observe("tool.kb_memory_delete.latency_ms", latency_ms)
        audit_tool(
            deps,
            auth=auth,
            tool="kb_memory_delete",
            params=payload.model_dump(),
            result_count=deleted,
            latency_ms=latency_ms,
            acl_decision="applied",
        )
        return KbMemoryDeleteOutput(deleted_count=deleted, meta={"latency_ms": latency_ms})
