from __future__ import annotations

from time import perf_counter
from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from kb_mcp.bootstrap import AppDeps, build_deps
from kb_mcp.observability.tracing import ensure_request_id
from kb_mcp.retrieval.rerank import RerankConfig
from kb_mcp.retrieval.router import POLICY_VERSION, QueryRouter
from kb_mcp.security.acl import AccessContext
from kb_mcp.security.auth import AuthResolution
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

FastContext = Context[Any, Any, Any]

RUNTIME_TOOL_POLICY_PROMPT = """Ты работаешь с MCP tools базы знаний.
Всегда сначала определяй intent и вызывай tools до финального ответа, если факт можно проверить.
Обязательный порядок:
1) kb.memory.search для user/workspace контекста;
2) kb.search для factual evidence и citations;
3) kb.graph_expand для зависимостей/impact;
4) kb.explain для объяснения релевантности.
Для новых фактов используй kb.memory.upsert только при наличии citations и confidence >= threshold.
Для удаления памяти используй только kb.memory.delete.
Не выдумывай источники: если evidence нет, явно сообщи это.
Если graph недоступен, деградируй на vector evidence и укажи ограничение."""


def _request_from_ctx(ctx: FastContext | None) -> Any | None:
    if ctx is None:
        return None
    try:
        req_ctx = ctx.request_context
    except Exception:
        return None
    return req_ctx.request if req_ctx is not None else None


def _legacy_acl(*, workspace_id: str, subject: str) -> dict[str, Any]:
    return {
        "workspace_id": workspace_id,
        "subject": subject,
        "roles": [],
        "jwt_bearer": None,
    }


def _resource_allowed(*, deps: AppDeps, auth_ctx: AccessContext, data: dict[str, Any]) -> bool:
    workspace_id = str(data.get("workspace_id", "")).strip()
    if workspace_id and workspace_id != auth_ctx.workspace_id:
        return False
    acl_allow_raw = data.get("acl_allow")
    acl_allow = [str(v) for v in acl_allow_raw] if isinstance(acl_allow_raw, list) else None
    return deps.acl.can_read(ctx=auth_ctx, acl_allow=acl_allow)


def create_mcp_server(deps: AppDeps | None = None) -> FastMCP:
    deps = deps or build_deps()
    cfg = deps.config

    transport_security = None
    if cfg.transport_security_enabled:
        allowed_hosts = list(cfg.transport_allowed_hosts) or [
            "127.0.0.1:*",
            "localhost:*",
            "[::1]:*",
        ]
        allowed_origins = list(cfg.transport_allowed_origins) or [
            "http://127.0.0.1:*",
            "http://localhost:*",
            "http://[::1]:*",
        ]
        transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=allowed_hosts,
            allowed_origins=allowed_origins,
        )

    mcp = FastMCP(
        cfg.service_name,
        stateless_http=True,
        json_response=True,
        host=cfg.http_host,
        port=cfg.http_port,
        streamable_http_path="/mcp",
        transport_security=transport_security,
    )
    router = QueryRouter()

    def resolve_identity(payload_acl: dict[str, Any] | None, ctx: FastContext | None) -> AuthResolution:
        return deps.auth.resolve_identity(
            request=_request_from_ctx(ctx),
            payload_acl=payload_acl,
            allow_legacy_payload=True,
        )

    def audit_tool(
        *,
        auth: AuthResolution,
        tool: str,
        params: dict[str, Any],
        result_count: int,
        latency_ms: int,
        acl_decision: str,
    ) -> None:
        deps.audit.log_call(
            subject=auth.ctx.subject,
            workspace_id=auth.ctx.workspace_id,
            tool=tool,
            params=params,
            result_count=result_count,
            latency_ms=latency_ms,
            auth_mode=auth.auth_mode,
            identity_source=auth.identity_source,
            acl_decision=acl_decision,
        )

    @mcp.tool(name="kb.search")
    def kb_search(payload: KbSearchInput, ctx: FastContext | None = None) -> KbSearchOutput:
        request_id = ensure_request_id()
        t0 = perf_counter()

        auth = resolve_identity(payload.filters.acl.model_dump(), ctx)
        acl_filters = deps.acl.apply_filters(ctx=auth.ctx, filters=payload.filters.model_dump())
        search_workspace = auth.ctx.workspace_id
        acl_filters["workspace_id"] = search_workspace

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
            },
            debug={
                "latency_ms": debug.latency_ms,
                "fallback_mode": debug.fallback_mode,
                "fallback_reason": debug.fallback_reason,
                "filters_applied": True,
                "deprecated_legacy_acl": auth.deprecated_legacy_acl,
                "payload_workspace_ignored": payload.workspace_id != auth.ctx.workspace_id,
            },
        )

        deps.metrics.inc("tool.kb.search.calls")
        latency_ms = int((perf_counter() - t0) * 1000)
        audit_tool(
            auth=auth,
            tool="kb.search",
            params=payload.model_dump(),
            result_count=len(results),
            latency_ms=latency_ms,
            acl_decision="applied",
        )
        return output

    @mcp.tool(name="kb.graph_expand")
    def kb_graph_expand(payload: KbGraphExpandInput, ctx: FastContext | None = None) -> KbGraphExpandOutput:
        t0 = perf_counter()
        auth = resolve_identity(_legacy_acl(workspace_id=payload.workspace_id, subject=payload.subject), ctx)
        filters: dict[str, object] = {"workspace_id": auth.ctx.workspace_id, "acl_subject": auth.ctx.subject}
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
        latency_ms = int((perf_counter() - t0) * 1000)
        audit_tool(
            auth=auth,
            tool="kb.graph_expand",
            params=payload.model_dump(),
            result_count=len(edges),
            latency_ms=latency_ms,
            acl_decision="applied",
        )
        return out

    @mcp.tool(name="kb.explain")
    def kb_explain(payload: KbExplainInput, ctx: FastContext | None = None) -> KbExplainOutput:
        t0 = perf_counter()
        auth = resolve_identity(_legacy_acl(workspace_id=payload.workspace_id, subject=payload.subject), ctx)
        filters: dict[str, object] = {"workspace_id": auth.ctx.workspace_id, "acl_subject": auth.ctx.subject}
        explanations: list[dict[str, Any]] = []
        for uri in payload.uris:
            graph_reasons = deps.graph_store.explain_uri(uri=uri, filters=filters)
            reasons = [{"type": "graph", "detail": reason} for reason in graph_reasons]
            reasons.insert(0, {"type": "vector", "detail": "score derived from vector similarity + fusion + rerank"})
            explanations.append({"uri": uri, "reasons": reasons})
        deps.metrics.inc("tool.kb.explain.calls")
        latency_ms = int((perf_counter() - t0) * 1000)
        audit_tool(
            auth=auth,
            tool="kb.explain",
            params=payload.model_dump(),
            result_count=len(explanations),
            latency_ms=latency_ms,
            acl_decision="applied",
        )
        return KbExplainOutput(explanations=explanations)

    @mcp.tool(name="kb.memory.upsert")
    def kb_memory_upsert(payload: KbMemoryUpsertInput, ctx: FastContext | None = None) -> KbMemoryUpsertOutput:
        t0 = perf_counter()
        auth = resolve_identity(_legacy_acl(workspace_id=payload.workspace_id, subject=payload.subject), ctx)
        stored_ids, report = deps.memory.upsert(
            workspace_id=auth.ctx.workspace_id,
            subject=auth.ctx.subject,
            session_id=payload.session_id,
            items=[item.model_dump() for item in payload.items],
        )
        deps.metrics.inc("tool.kb.memory.upsert.calls")
        latency_ms = int((perf_counter() - t0) * 1000)
        audit_tool(
            auth=auth,
            tool="kb.memory.upsert",
            params=payload.model_dump(),
            result_count=len(stored_ids),
            latency_ms=latency_ms,
            acl_decision="applied",
        )
        return KbMemoryUpsertOutput(stored_ids=stored_ids, validation_report=report)

    @mcp.tool(name="kb.memory.search")
    def kb_memory_search(payload: KbMemorySearchInput, ctx: FastContext | None = None) -> KbMemorySearchOutput:
        t0 = perf_counter()
        auth = resolve_identity(_legacy_acl(workspace_id=payload.workspace_id, subject=payload.subject), ctx)
        hits = deps.memory.search(
            query=payload.query,
            workspace_id=auth.ctx.workspace_id,
            subject=auth.ctx.subject,
            top_k=payload.top_k,
        )
        deps.metrics.inc("tool.kb.memory.search.calls")
        latency_ms = int((perf_counter() - t0) * 1000)
        audit_tool(
            auth=auth,
            tool="kb.memory.search",
            params=payload.model_dump(),
            result_count=len(hits),
            latency_ms=latency_ms,
            acl_decision="applied",
        )
        return KbMemorySearchOutput(
            results=[
                MemoryHit(uri=hit.uri, score=hit.score, text=deps.redact.redact(hit.text), citations=hit.citations)
                for hit in hits
            ]
        )

    @mcp.tool(name="kb.memory.delete")
    def kb_memory_delete(payload: KbMemoryDeleteInput, ctx: FastContext | None = None) -> KbMemoryDeleteOutput:
        t0 = perf_counter()
        auth = resolve_identity(_legacy_acl(workspace_id=payload.workspace_id, subject=payload.subject), ctx)
        deleted = deps.memory.delete(
            workspace_id=auth.ctx.workspace_id,
            subject=auth.ctx.subject,
            ids=payload.ids,
            all_for_subject=payload.all_for_subject,
        )
        deps.metrics.inc("tool.kb.memory.delete.calls")
        latency_ms = int((perf_counter() - t0) * 1000)
        audit_tool(
            auth=auth,
            tool="kb.memory.delete",
            params=payload.model_dump(),
            result_count=deleted,
            latency_ms=latency_ms,
            acl_decision="applied",
        )
        return KbMemoryDeleteOutput(deleted_count=deleted)

    @mcp.tool(name="kb.ingest.filesystem")
    def kb_ingest_filesystem(
        root_path: str,
        workspace_id: str,
        acl_subject: str,
        ctx: FastContext | None = None,
    ) -> dict[str, int]:
        t0 = perf_counter()
        auth = resolve_identity(_legacy_acl(workspace_id=workspace_id, subject=acl_subject), ctx)
        result = deps.ingestion.ingest_filesystem(
            root=root_path,
            workspace_id=auth.ctx.workspace_id,
            acl_allow=[auth.ctx.subject],
        )
        deps.metrics.inc("tool.kb.ingest.filesystem.calls")
        latency_ms = int((perf_counter() - t0) * 1000)
        audit_tool(
            auth=auth,
            tool="kb.ingest.filesystem",
            params={"root_path": root_path, "workspace_id": workspace_id, "acl_subject": acl_subject},
            result_count=result.get("created", 0) + result.get("updated", 0),
            latency_ms=latency_ms,
            acl_decision="applied",
        )
        return result

    @mcp.tool(name="kb.ingest.git_diff")
    def kb_ingest_git_diff(
        repo_root: str,
        workspace_id: str,
        acl_subject: str,
        since_ref: str = "HEAD~1",
        ctx: FastContext | None = None,
    ) -> dict[str, int]:
        t0 = perf_counter()
        auth = resolve_identity(_legacy_acl(workspace_id=workspace_id, subject=acl_subject), ctx)
        result = deps.ingestion.ingest_git_diff(
            root=repo_root,
            workspace_id=auth.ctx.workspace_id,
            acl_allow=[auth.ctx.subject],
            since_ref=since_ref,
        )
        deps.metrics.inc("tool.kb.ingest.git_diff.calls")
        latency_ms = int((perf_counter() - t0) * 1000)
        audit_tool(
            auth=auth,
            tool="kb.ingest.git_diff",
            params={
                "repo_root": repo_root,
                "workspace_id": workspace_id,
                "acl_subject": acl_subject,
                "since_ref": since_ref,
            },
            result_count=result.get("created", 0) + result.get("updated", 0),
            latency_ms=latency_ms,
            acl_decision="applied",
        )
        return result

    @mcp.resource("kb://doc/{doc_id}")
    def resource_doc(doc_id: str, ctx: FastContext | None = None) -> dict[str, Any]:
        uri = f"kb://doc/{doc_id}"
        doc = deps.metadata.get_doc(uri)
        if doc is None:
            return {"error": "not_found", "uri": uri}
        auth = deps.auth.resolve_identity(
            request=_request_from_ctx(ctx),
            payload_acl=None,
            allow_legacy_payload=False,
        )
        if not _resource_allowed(deps=deps, auth_ctx=auth.ctx, data=doc):
            return {"error": "forbidden", "uri": uri}
        out = dict(doc)
        if "text" in out:
            out["text"] = deps.redact.redact(str(out["text"]))
        return out

    @mcp.resource("kb://chunk/{chunk_id}")
    def resource_chunk(chunk_id: str, ctx: FastContext | None = None) -> dict[str, Any]:
        uri = f"kb://chunk/{chunk_id}"
        chunk = deps.metadata.get_chunk(uri)
        if chunk is None:
            return {"error": "not_found", "uri": uri}
        auth = deps.auth.resolve_identity(
            request=_request_from_ctx(ctx),
            payload_acl=None,
            allow_legacy_payload=False,
        )
        if not _resource_allowed(deps=deps, auth_ctx=auth.ctx, data=chunk):
            return {"error": "forbidden", "uri": uri}
        out = dict(chunk)
        out["text"] = deps.redact.redact(str(out.get("text", "")))
        return out

    @mcp.resource("kb://entity/{entity_id}")
    def resource_entity(entity_id: str, ctx: FastContext | None = None) -> dict[str, Any]:
        uri = f"kb://entity/{entity_id}"
        entity = deps.metadata.get_entity(uri)
        if entity is None:
            return {"uri": uri, "type": "Entity", "name": entity_id, "links": []}
        auth = deps.auth.resolve_identity(
            request=_request_from_ctx(ctx),
            payload_acl=None,
            allow_legacy_payload=False,
        )
        if not _resource_allowed(deps=deps, auth_ctx=auth.ctx, data=entity):
            return {"error": "forbidden", "uri": uri}
        return entity

    @mcp.resource("kb://memory/{memory_id}")
    def resource_memory(memory_id: str, ctx: FastContext | None = None) -> dict[str, Any]:
        uri = f"kb://memory/{memory_id}"
        memory = deps.metadata.get_memory(uri)
        if memory is None:
            return {"error": "not_found", "uri": uri}
        auth = deps.auth.resolve_identity(
            request=_request_from_ctx(ctx),
            payload_acl=None,
            allow_legacy_payload=False,
        )
        if not _resource_allowed(deps=deps, auth_ctx=auth.ctx, data=memory):
            return {"error": "forbidden", "uri": uri}
        out = dict(memory)
        out["text"] = deps.redact.redact(str(out.get("text", "")))
        return out

    @mcp.resource("kb://policy/tool-selection")
    def resource_tool_selection_policy() -> dict[str, Any]:
        return {
            "version": POLICY_VERSION,
            "intent_catalog": [
                "fact_lookup",
                "relation_impact",
                "explainability",
                "memory_context",
                "memory_delete",
            ],
            "priority_tools": [
                "kb.memory.search",
                "kb.search",
                "kb.graph_expand",
                "kb.explain",
            ],
            "memory_write_constraints": {
                "tool": "kb.memory.upsert",
                "requires_citations": True,
                "requires_confidence_threshold": True,
            },
            "fallback_policy": "When graph backend is unavailable, return vector-only evidence with explicit limitation.",
        }

    @mcp.prompt(name="kb.answer_with_citations")
    def prompt_answer_with_citations(question: str) -> str:
        return (
            "Ответь на вопрос только на основании evidence. "
            "Для каждого утверждения дай citation на kb://chunk/... и span. "
            f"Вопрос: {question}"
        )

    @mcp.prompt(name="kb.tool_selection_policy")
    def prompt_tool_selection_policy() -> str:
        return RUNTIME_TOOL_POLICY_PROMPT

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
