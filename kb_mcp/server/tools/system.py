from __future__ import annotations

from time import perf_counter
from typing import Any
from mcp.server.fastmcp import FastMCP
from kb_mcp.server.helpers import FastContext

from kb_mcp.retrieval.router import QueryRouter, POLICY_VERSION
from kb_mcp.server.schemas import (
    KbHealthOutput,
    KbRouteInput,
    KbRouteOutput,
)
from kb_mcp.server.helpers import (
    audit_tool,
    request_from_ctx,
    with_middlewares,
)
from kb_mcp.retrieval.execution_plan import build_execution_plan

def register_system_tools(
    mcp: FastMCP,
    deps: Any,
    registered_tools: list[str],
    registered_resources: list[str],
    registered_prompts: list[str],
) -> None:
    cfg = deps.config
    router = QueryRouter()

    @mcp.tool(name="kb_health")
    @with_middlewares("kb_health", deps)
    def kb_health(ctx: FastContext | None = None) -> KbHealthOutput:
        """Get the health status, configurations, backends, and registered capabilities of the knowledge base service."""
        _ = ctx
        return KbHealthOutput(
            service_name=cfg.service_name,
            transport="mcp",
            auth_mode=cfg.auth_mode,
            backends={
                "vector": cfg.vector_backend,
                "graph": cfg.graph_backend,
                "metadata": cfg.metadata_backend,
                "embedding": cfg.embedding_provider,
            },
            tools=list(registered_tools),
            resources=list(registered_resources),
            prompts=list(registered_prompts),
            config={
                "http_host": cfg.http_host,
                "http_port": cfg.http_port,
                "transport_security_enabled": cfg.transport_security_enabled,
                "graph_enforce_object_acl": cfg.graph_enforce_object_acl,
                "auto_ingest_enabled": cfg.auto_ingest_enabled,
                "ingest_allowed_roots": list(cfg.ingest_allowed_roots),
                "max_top_k": cfg.max_top_k,
                "max_expand_depth": cfg.max_expand_depth,
            },
            embedding_info={
                "model": cfg.embedding_model,
                "dimensions": cfg.embedding_dimensions,
                "provider": cfg.embedding_provider,
                "query_prefix": cfg.embedding_query_prefix,
                "passage_prefix": cfg.embedding_passage_prefix,
                "cache_enabled": cfg.embedding_cache_enabled,
                "cache_max_items": cfg.embedding_cache_max_items,
                "chunking_mode": cfg.chunking_mode,
            },
            meta={"policy_version": POLICY_VERSION},
        )

    @mcp.tool(name="kb_route")
    @with_middlewares("kb_route", deps)
    def kb_route(payload: KbRouteInput, ctx: FastContext | None = None) -> KbRouteOutput:
        """Route the input query to determine the best retrieval intent, mode, and target tools, returning an execution plan."""
        t0 = perf_counter()
        auth = deps.auth.resolve_identity(
            request=request_from_ctx(ctx),
            payload_acl=None,
            allow_legacy_payload=True,
        )
        routed = router.route(
            payload.query,
            payload.requested_mode,
            include_memory=payload.include_memory,
        )
        out = KbRouteOutput(
            policy_version=POLICY_VERSION,
            intent=routed.intent,
            mode=routed.mode,
            route_reason=routed.reason,
            recommended_tools=list(routed.recommended_tools),
            execution_plan=build_execution_plan(intent=routed.intent),
            constraints={
                "memory_write": {
                    "tool": "kb_memory_upsert",
                    "requires_citations": True,
                    "requires_confidence_threshold": True,
                },
                "prompts_optional": True,
            },
        )
        deps.metrics.inc("tool.kb_route.calls")
        latency_ms = int((perf_counter() - t0) * 1000)
        out.meta = {"latency_ms": latency_ms, "policy_version": POLICY_VERSION}
        deps.metrics.observe("tool.kb_route.latency_ms", latency_ms)
        audit_tool(
            deps,
            auth=auth,
            tool="kb_route",
            params=payload.model_dump(),
            result_count=len(out.recommended_tools),
            latency_ms=latency_ms,
            acl_decision="n/a",
        )
        return out


