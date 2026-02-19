from __future__ import annotations

import uuid
from time import perf_counter
from typing import Any

from mcp.server.fastmcp import FastMCP

from kb_mcp.bootstrap import AppDeps, build_deps
from kb_mcp.observability.tracing import ensure_request_id
from kb_mcp.retrieval.rerank import RerankConfig
from kb_mcp.retrieval.router import QueryRouter
from kb_mcp.security.acl import AccessContext
from kb_mcp.server.schemas import (
    Citation,
    EntityRef,
    KbExplainInput,
    KbExplainOutput,
    KbGraphExpandInput,
    KbGraphExpandOutput,
    KbMemoryDeleteInput,
    KbMemoryDeleteOutput,
    KbMemorySearchInput,
    KbMemorySearchOutput,
    KbMemoryUpsertInput,
    KbMemoryUpsertOutput,
    KbSearchInput,
    KbSearchOutput,
    MemoryHit,
    SearchResult,
)


def _ctx_from_acl(deps: AppDeps, acl: dict[str, Any]) -> AccessContext:
    token = acl.get("jwt_bearer")
    if isinstance(token, str) and token:
        parsed = deps.auth.parse_bearer(token)
        if parsed.ok and parsed.ctx is not None:
            return parsed.ctx

    return AccessContext(
        subject=str(acl.get("subject", "anonymous")),
        roles=tuple(str(role) for role in acl.get("roles", [])),
        workspace_id=str(acl.get("workspace_id", "default")),
    )


def create_mcp_server(deps: AppDeps | None = None) -> FastMCP:
    deps = deps or build_deps()
    cfg = deps.config

    mcp = FastMCP(
        cfg.service_name,
        stateless_http=True,
        json_response=True,
        host=cfg.http_host,
        port=cfg.http_port,
        streamable_http_path="/mcp",
    )
    router = QueryRouter()

    @mcp.tool(name="kb.search")
    def kb_search(payload: KbSearchInput) -> KbSearchOutput:
        request_id = ensure_request_id()
        t0 = perf_counter()

        ctx = _ctx_from_acl(deps, payload.filters.acl.model_dump())
        filters = deps.acl.apply_filters(ctx=ctx, filters=payload.filters.model_dump())
        filters["workspace_id"] = payload.workspace_id

        memory_hits = deps.memory.search(
            query=payload.query,
            workspace_id=payload.workspace_id,
            subject=ctx.subject,
            top_k=min(5, payload.top_k),
        ) if payload.include_memory else []

        memory_bonus_by_uri: dict[str, float] = {}
        for hit in memory_hits:
            for citation in hit.citations:
                chunk_uri = citation.get("chunk_uri")
                if isinstance(chunk_uri, str):
                    memory_bonus_by_uri[chunk_uri] = max(memory_bonus_by_uri.get(chunk_uri, 0.0), hit.score)

        routed = router.route(payload.query, payload.mode)
        rerank_cfg = RerankConfig(
            enabled=payload.rerank.enabled,
            provider=payload.rerank.provider,
            top_n=payload.rerank.top_n,
        )

        depth = payload.graph.expand_depth if routed.mode != "vector" else 0
        edge_types = payload.graph.edge_types if routed.mode != "vector" else []

        items, debug = deps.retriever.search(
            query=payload.query,
            top_k=min(payload.top_k, cfg.max_top_k),
            filters=filters,
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

        output = KbSearchOutput(
            query_id=str(uuid.uuid4()),
            results=results,
            memory_hits=[
                MemoryHit(uri=hit.uri, score=hit.score, text=deps.redact.redact(hit.text), citations=hit.citations)
                for hit in memory_hits
            ],
            decision_trace={
                "request_id": request_id,
                "mode": routed.mode,
                "route_reason": routed.reason,
                "rerank_provider": payload.rerank.provider,
            },
            debug={
                "latency_ms": debug.latency_ms,
                "fallback_mode": debug.fallback_mode,
                "fallback_reason": debug.fallback_reason,
                "filters_applied": True,
            },
        )

        deps.metrics.inc("tool.kb.search.calls")
        latency_ms = int((perf_counter() - t0) * 1000)
        deps.audit.log_call(
            subject=ctx.subject,
            workspace_id=payload.workspace_id,
            tool="kb.search",
            params=payload.model_dump(),
            result_count=len(results),
            latency_ms=latency_ms,
        )
        return output

    @mcp.tool(name="kb.graph_expand")
    def kb_graph_expand(payload: KbGraphExpandInput) -> KbGraphExpandOutput:
        filters: dict[str, object] = {"workspace_id": payload.workspace_id, "acl_subject": payload.subject}
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
        deps.metrics.inc("tool.kb.graph_expand.calls")
        return out

    @mcp.tool(name="kb.explain")
    def kb_explain(payload: KbExplainInput) -> KbExplainOutput:
        filters: dict[str, object] = {"workspace_id": payload.workspace_id, "acl_subject": payload.subject}
        explanations: list[dict[str, Any]] = []
        for uri in payload.uris:
            graph_reasons = deps.graph_store.explain_uri(uri=uri, filters=filters)
            reasons = [{"type": "graph", "detail": reason} for reason in graph_reasons]
            reasons.insert(0, {"type": "vector", "detail": "score derived from vector similarity + fusion + rerank"})
            explanations.append({"uri": uri, "reasons": reasons})
        deps.metrics.inc("tool.kb.explain.calls")
        return KbExplainOutput(explanations=explanations)

    @mcp.tool(name="kb.memory.upsert")
    def kb_memory_upsert(payload: KbMemoryUpsertInput) -> KbMemoryUpsertOutput:
        stored_ids, report = deps.memory.upsert(
            workspace_id=payload.workspace_id,
            subject=payload.subject,
            session_id=payload.session_id,
            items=[item.model_dump() for item in payload.items],
        )
        deps.metrics.inc("tool.kb.memory.upsert.calls")
        return KbMemoryUpsertOutput(stored_ids=stored_ids, validation_report=report)

    @mcp.tool(name="kb.memory.search")
    def kb_memory_search(payload: KbMemorySearchInput) -> KbMemorySearchOutput:
        hits = deps.memory.search(
            query=payload.query,
            workspace_id=payload.workspace_id,
            subject=payload.subject,
            top_k=payload.top_k,
        )
        deps.metrics.inc("tool.kb.memory.search.calls")
        return KbMemorySearchOutput(
            results=[
                MemoryHit(uri=hit.uri, score=hit.score, text=deps.redact.redact(hit.text), citations=hit.citations)
                for hit in hits
            ]
        )

    @mcp.tool(name="kb.memory.delete")
    def kb_memory_delete(payload: KbMemoryDeleteInput) -> KbMemoryDeleteOutput:
        deleted = deps.memory.delete(
            workspace_id=payload.workspace_id,
            subject=payload.subject,
            ids=payload.ids,
            all_for_subject=payload.all_for_subject,
        )
        deps.metrics.inc("tool.kb.memory.delete.calls")
        return KbMemoryDeleteOutput(deleted_count=deleted)

    @mcp.tool(name="kb.ingest.filesystem")
    def kb_ingest_filesystem(root_path: str, workspace_id: str, acl_subject: str) -> dict[str, int]:
        result = deps.ingestion.ingest_filesystem(root=root_path, workspace_id=workspace_id, acl_allow=[acl_subject])
        deps.metrics.inc("tool.kb.ingest.filesystem.calls")
        return result

    @mcp.resource("kb://doc/{doc_id}")
    def resource_doc(doc_id: str) -> dict[str, Any]:
        uri = f"kb://doc/{doc_id}"
        doc = deps.metadata.get_doc(uri)
        if doc is None:
            return {"error": "not_found", "uri": uri}
        out = dict(doc)
        if "text" in out:
            out["text"] = deps.redact.redact(str(out["text"]))
        return out

    @mcp.resource("kb://chunk/{chunk_id}")
    def resource_chunk(chunk_id: str) -> dict[str, Any]:
        uri = f"kb://chunk/{chunk_id}"
        chunk = deps.metadata.get_chunk(uri)
        if chunk is None:
            return {"error": "not_found", "uri": uri}
        out = dict(chunk)
        out["text"] = deps.redact.redact(str(out.get("text", "")))
        return out

    @mcp.resource("kb://entity/{entity_id}")
    def resource_entity(entity_id: str) -> dict[str, Any]:
        uri = f"kb://entity/{entity_id}"
        entity = deps.metadata.get_entity(uri)
        if entity is None:
            return {"uri": uri, "type": "Entity", "name": entity_id, "links": []}
        return entity

    @mcp.resource("kb://memory/{memory_id}")
    def resource_memory(memory_id: str) -> dict[str, Any]:
        uri = f"kb://memory/{memory_id}"
        memory = deps.metadata.get_memory(uri)
        if memory is None:
            return {"error": "not_found", "uri": uri}
        out = dict(memory)
        out["text"] = deps.redact.redact(str(out.get("text", "")))
        return out

    @mcp.prompt(name="kb.answer_with_citations")
    def prompt_answer_with_citations(question: str) -> str:
        return (
            "Ответь на вопрос только на основании evidence. "
            "Для каждого утверждения дай citation на kb://chunk/... и span. "
            f"Вопрос: {question}"
        )

    @mcp.prompt(name="kb.incident_triage")
    def prompt_incident_triage(incident: str) -> str:
        return (
            "Сделай triage инцидента: симптомы, вероятные причины, зависимости, runbook steps. "
            "Каждый шаг должен ссылаться на evidence. "
            f"Инцидент: {incident}"
        )

    @mcp.prompt(name="kb.memory_grounded_reply")
    def prompt_memory_grounded_reply(question: str) -> str:
        return (
            "Сформируй ответ, сначала опираясь на memory_hits текущего пользователя/workspace, "
            "затем проверь ответ через документальные evidence и приложи citations. "
            f"Вопрос: {question}"
        )

    return mcp
