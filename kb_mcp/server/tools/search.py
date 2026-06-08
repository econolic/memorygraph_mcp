from __future__ import annotations

from time import perf_counter
from typing import Any
from mcp.server.fastmcp import FastMCP
from kb_mcp.server.helpers import FastContext

from kb_mcp.observability.tracing import ensure_request_id, start_span
from kb_mcp.retrieval.rerank import RerankConfig
from kb_mcp.retrieval.router import QueryRouter, POLICY_VERSION
from kb_mcp.server.schemas import (
    Citation,
    EntityRef,
    KbExplainInput,
    KbExplainOutput,
    KbGraphExpandInput,
    KbGraphExpandOutput,
    KbSearchInput,
    KbSearchOutput,
    MemoryHit,
    SearchResult,
)
from kb_mcp.server.helpers import (
    resolve_identity,
    audit_tool,
    legacy_acl,
    normalize_datetime_utc,
    with_middlewares,
)

def register_search_tools(mcp: FastMCP, deps: Any) -> None:
    cfg = deps.config
    router = QueryRouter()

    @mcp.tool(name="kb_search")
    @with_middlewares("kb_search", deps)
    def kb_search(payload: KbSearchInput, ctx: FastContext | None = None) -> KbSearchOutput:
        """Search the knowledge base using hybrid retrieval (vector + graph + memory) with ACL filtering."""
        request_id = ensure_request_id()
        t0 = perf_counter()

        auth = resolve_identity(deps, payload.filters.acl.model_dump(), ctx)
        acl_filters = deps.acl.apply_filters(ctx=auth.ctx, filters=payload.filters.model_dump())
        search_workspace = auth.ctx.workspace_id
        acl_filters["workspace_id"] = search_workspace
        acl_filters["graph_enforce_object_acl"] = cfg.graph_enforce_object_acl

        memory_hits = deps.memory.search(
            query=payload.query,
            workspace_id=search_workspace,
            subject=auth.ctx.subject,
            top_k=min(5, payload.top_k),
        ) if payload.include_memory else []

        memory_bonus_by_uri: dict[str, float] = {}
        for hit in memory_hits:
            for citation in hit.citations:
                chunk_uri = citation.get("chunk_uri")
                if isinstance(chunk_uri, str):
                    memory_bonus_by_uri[chunk_uri] = max(memory_bonus_by_uri.get(chunk_uri, 0.0), hit.score)

        routed = router.route(payload.query, payload.mode, include_memory=payload.include_memory)
        rerank_cfg = RerankConfig(
            enabled=payload.rerank.enabled,
            provider=payload.rerank.provider,
            top_n=payload.rerank.top_n,
        )

        depth = payload.graph.expand_depth if routed.mode != "vector" else 0
        edge_types = payload.graph.edge_types if routed.mode != "vector" else []

        with start_span(
            "tool.kb_search",
            attributes={
                "tool.name": "kb_search",
                "workspace_id": search_workspace,
                "mode": routed.mode,
            },
        ):
            items, debug = deps.retriever.search(
                query=payload.query,
                top_k=min(payload.top_k, cfg.max_top_k),
                filters=acl_filters,
                depth=min(depth, cfg.max_expand_depth),
                edge_types=edge_types,
                max_nodes=payload.graph.max_nodes,
                memory_bonus_by_uri=memory_bonus_by_uri,
                rerank=rerank_cfg,
            )

        results: list[SearchResult] = []
        for item in items:
            ev = deps.evidence.build(uri=item.uri, score=item.score, breakdown=item.score_breakdown)
            results.append(
                SearchResult(
                    uri=ev.uri,
                    title=ev.title,
                    snippet=deps.redact.redact(ev.snippet),
                    score=ev.score,
                    score_breakdown=ev.score_breakdown,
                    citations=[Citation.model_validate(citation) for citation in ev.citations],
                    entities=[EntityRef.model_validate(entity) for entity in ev.entities],
                )
            )

        acl_roles_raw = acl_filters.get("acl_roles", [])
        acl_roles = [str(role) for role in acl_roles_raw] if isinstance(acl_roles_raw, list) else []
        tags_raw = acl_filters.get("tags", [])
        tags = [str(tag) for tag in tags_raw] if isinstance(tags_raw, list) else []
        sources_raw = acl_filters.get("sources", [])
        sources = [str(source) for source in sources_raw] if isinstance(sources_raw, list) else []

        output = KbSearchOutput(
            query_id=request_id,
            results=results,
            memory_hits=[
                MemoryHit(uri=hit.uri, score=hit.score, text=deps.redact.redact(hit.text), citations=hit.citations)
                for hit in memory_hits
            ],
            decision_trace={
                "request_id": request_id,
                "mode": routed.mode,
                "route_reason": routed.reason,
                "intent": routed.intent,
                "recommended_tools": list(routed.recommended_tools),
                "policy_version": POLICY_VERSION,
                "auth_mode": auth.auth_mode,
                "identity_source": auth.identity_source,
                "rerank_provider": payload.rerank.provider,
                "fusion_mode": debug.fusion_mode,
            },
            debug={
                "latency_ms": debug.latency_ms,
                "fallback_mode": debug.fallback_mode,
                "fallback_reason": debug.fallback_reason,
                "filters_applied": True,
                "filters_effective": {
                    "workspace_id": str(acl_filters.get("workspace_id", "")),
                    "acl_subject": str(acl_filters.get("acl_subject", "")),
                    "acl_roles": acl_roles,
                    "tags": tags,
                    "sources": sources,
                    "updated_after": normalize_datetime_utc(acl_filters.get("updated_after")),
                },
                "graph_acl_enforced": cfg.graph_enforce_object_acl,
                "fusion_mode": debug.fusion_mode,
                "graph_seed_count": debug.graph_seed_count,
                "graph_node_count": debug.graph_node_count,
                "graph_chunk_bonus_count": debug.graph_chunk_bonus_count,
                "graph_nonzero": debug.graph_nonzero,
                "deprecated_legacy_acl": auth.deprecated_legacy_acl,
                "payload_workspace_ignored": payload.workspace_id != auth.ctx.workspace_id,
            },
        )

        deps.metrics.inc("tool.kb_search.calls")
        latency_ms = int((perf_counter() - t0) * 1000)
        output.meta = {"latency_ms": latency_ms, "request_id": request_id}
        deps.metrics.observe("tool.kb_search.latency_ms", latency_ms)
        for stage, value_ms in debug.latency_ms.items():
            deps.metrics.observe("retrieval.stage.latency_ms", value_ms, labels={"stage": stage})
        audit_tool(
            deps,
            auth=auth,
            tool="kb_search",
            params=payload.model_dump(),
            result_count=len(results),
            latency_ms=latency_ms,
            acl_decision="applied",
        )
        return output

    @mcp.tool(name="kb_graph_expand")
    @with_middlewares("kb_graph_expand", deps)
    def kb_graph_expand(payload: KbGraphExpandInput, ctx: FastContext | None = None) -> KbGraphExpandOutput:
        """Expand and retrieve entities and relations starting from seed entities in the knowledge graph."""
        t0 = perf_counter()
        auth = resolve_identity(deps, legacy_acl(workspace_id=payload.workspace_id, subject=payload.subject), ctx)
        filters: dict[str, object] = {
            "workspace_id": auth.ctx.workspace_id,
            "acl_subject": auth.ctx.subject,
            "acl_roles": list(auth.ctx.roles),
            "graph_enforce_object_acl": cfg.graph_enforce_object_acl,
        }
        nodes, edges = deps.graph_store.expand(
            seed_uris=payload.seed_entities,
            depth=payload.depth,
            edge_types=payload.edge_types,
            max_nodes=payload.max_nodes,
            filters=filters,
        )
        paths = [[edge.src, edge.rel, edge.dst] for edge in edges]
        out = KbGraphExpandOutput(
            nodes=[{"uri": n.uri, "type": n.type, "name": n.name, **n.properties} for n in nodes],
            edges=[{"src": e.src, "rel": e.rel, "dst": e.dst} for e in edges],
            paths=paths,
        )
        deps.metrics.inc("tool.kb_graph_expand.calls")
        latency_ms = int((perf_counter() - t0) * 1000)
        out.meta = {"latency_ms": latency_ms}
        deps.metrics.observe("tool.kb_graph_expand.latency_ms", latency_ms)
        audit_tool(
            deps,
            auth=auth,
            tool="kb_graph_expand",
            params=payload.model_dump(),
            result_count=len(edges),
            latency_ms=latency_ms,
            acl_decision="applied",
        )
        return out

    @mcp.tool(name="kb_explain")
    @with_middlewares("kb_explain", deps)
    def kb_explain(payload: KbExplainInput, ctx: FastContext | None = None) -> KbExplainOutput:
        """Provide detailed retrieval explanations/reasons for specific document or chunk URIs."""
        t0 = perf_counter()
        auth = resolve_identity(deps, legacy_acl(workspace_id=payload.workspace_id, subject=payload.subject), ctx)
        filters: dict[str, object] = {
            "workspace_id": auth.ctx.workspace_id,
            "acl_subject": auth.ctx.subject,
            "acl_roles": list(auth.ctx.roles),
            "graph_enforce_object_acl": cfg.graph_enforce_object_acl,
        }
        explanations: list[dict[str, Any]] = []
        for uri in payload.uris:
            graph_reasons = deps.graph_store.explain_uri(uri=uri, filters=filters)
            reasons = [{"type": "graph", "detail": reason} for reason in graph_reasons]
            reasons.insert(0, {"type": "vector", "detail": "score derived from vector similarity + fusion + rerank"})
            explanations.append({"uri": uri, "reasons": reasons})
        deps.metrics.inc("tool.kb_explain.calls")
        latency_ms = int((perf_counter() - t0) * 1000)
        deps.metrics.observe("tool.kb_explain.latency_ms", latency_ms)
        audit_tool(
            deps,
            auth=auth,
            tool="kb_explain",
            params=payload.model_dump(),
            result_count=len(explanations),
            latency_ms=latency_ms,
            acl_decision="applied",
        )
        return KbExplainOutput(explanations=explanations, meta={"latency_ms": latency_ms})
