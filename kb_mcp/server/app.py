from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING, Any, cast

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.auth.settings import AuthSettings
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import AnyHttpUrl

from kb_mcp.bootstrap import AppDeps, build_deps
from kb_mcp.observability.tracing import ensure_request_id, start_span
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
    KbHealthOutput,
    KbIngestOutput,
    KbMemoryDeleteInput,
    KbMemoryDeleteOutput,
    KbMemorySearchInput,
    KbMemorySearchOutput,
    KbMemoryUpsertInput,
    KbMemoryUpsertOutput,
    KbRouteInput,
    KbRouteOutput,
    KbRoutePlanStep,
    KbSearchInput,
    KbSearchOutput,
    MemoryHit,
    SearchResult,
)

if TYPE_CHECKING:
    FastContext = Context[Any, Any, Any]
else:
    FastContext = Context

RUNTIME_TOOL_POLICY_PROMPT = """Ты работаешь с MCP tools базы знаний.
Всегда сначала вызывай kb.route, затем следуй execution_plan и вызывай tools до финального ответа, если факт можно проверить.
Обязательный порядок:
0) kb.route для определения intent и плана;
1) kb.memory.search для user/workspace контекста;
2) kb.search для factual evidence и citations;
3) kb.graph_expand для зависимостей/impact;
4) kb.explain для объяснения релевантности.
Для новых фактов используй kb.memory.upsert только при наличии citations и confidence >= threshold.
Для удаления памяти используй только kb.memory.delete.
Не выдумывай источники: если evidence нет, явно сообщи это.
Если graph недоступен, деградируй на vector evidence и укажи ограничение."""

REGISTERED_TOOLS = [
    "kb.health",
    "kb.route",
    "kb.search",
    "kb.graph_expand",
    "kb.explain",
    "kb.memory.upsert",
    "kb.memory.search",
    "kb.memory.delete",
    "kb.ingest.filesystem",
    "kb.ingest.git_diff",
]

REGISTERED_RESOURCES = [
    "kb://doc/{doc_id}",
    "kb://chunk/{chunk_id}",
    "kb://entity/{entity_id}",
    "kb://memory/{memory_id}",
    "kb://policy/tool-selection",
]

REGISTERED_PROMPTS = [
    "kb.answer_with_citations",
    "kb.tool_selection_policy",
    "kb.incident_triage",
    "kb.memory_grounded_reply",
]


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


def _normalize_datetime_utc(value: object) -> str | None:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and value.strip():
        raw = value.strip()
        if raw.endswith("Z"):
            raw = f"{raw[:-1]}+00:00"
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _resource_server_url(*, host: str, port: int) -> str:
    normalized = host.strip() or "127.0.0.1"
    if normalized in {"0.0.0.0", "::"}:
        normalized = "127.0.0.1"
    if ":" in normalized and not normalized.startswith("["):
        normalized = f"[{normalized}]"
    return f"http://{normalized}:{port}"


def _contract_ok(data: dict[str, Any]) -> dict[str, Any]:
    out = dict(data)
    out.setdefault("ok", True)
    out.setdefault("error_code", None)
    out.setdefault("error_detail", None)
    out.setdefault("meta", {})
    return out


def _contract_error(*, uri: str, legacy_error: str, error_code: str, detail: str) -> dict[str, Any]:
    return {
        "error": legacy_error,
        "uri": uri,
        "ok": False,
        "error_code": error_code,
        "error_detail": detail,
        "meta": {},
    }


def _result_int(result: dict[str, object], key: str) -> int:
    value = result.get(key, 0)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return 0


def _path_allowed(path: str, allowed_roots: tuple[str, ...]) -> tuple[bool, str]:
    resolved = Path(path).expanduser().resolve()
    if not allowed_roots:
        return True, str(resolved)
    for root in allowed_roots:
        allowed = Path(root).expanduser().resolve()
        if resolved == allowed or allowed in resolved.parents:
            return True, str(resolved)
    return False, str(resolved)


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

    token_verifier = None
    auth_settings = None
    if cfg.auth_mode == "strict_oauth":
        token_verifier = deps.auth.oauth_token_verifier()
        if token_verifier is None:
            raise ValueError(
                "strict_oauth requires KB_OAUTH_ISSUER_URL and KB_OAUTH_JWKS_URL to be configured"
            )
        auth_settings = AuthSettings(
            issuer_url=cast(AnyHttpUrl, cfg.oauth_issuer_url),
            resource_server_url=cast(
                AnyHttpUrl,
                _resource_server_url(host=cfg.http_host, port=cfg.http_port),
            ),
            required_scopes=list(cfg.oauth_required_scopes) or None,
        )

    mcp = FastMCP(
        cfg.service_name,
        token_verifier=token_verifier,
        stateless_http=True,
        json_response=True,
        host=cfg.http_host,
        port=cfg.http_port,
        streamable_http_path="/mcp",
        auth=auth_settings,
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

    def build_execution_plan(*, intent: str) -> list[KbRoutePlanStep]:
        if intent == "memory_delete":
            return [
                KbRoutePlanStep(
                    tool="kb.memory.delete",
                    purpose="Delete stored memory for selected IDs or all records for current subject/workspace.",
                )
            ]
        if intent == "memory_context":
            return [
                KbRoutePlanStep(
                    tool="kb.memory.search",
                    purpose="Load prior user/workspace memory relevant to the question.",
                ),
                KbRoutePlanStep(
                    tool="kb.search",
                    purpose="Validate or enrich the answer with document evidence and citations.",
                ),
            ]
        if intent == "relation_impact":
            return [
                KbRoutePlanStep(
                    tool="kb.search",
                    purpose="Find evidence and candidate entities/URIs for graph expansion.",
                ),
                KbRoutePlanStep(
                    tool="kb.graph_expand",
                    purpose="Expand dependencies / impact paths from selected seed entities.",
                    when="after selecting seed entity URIs from search results",
                ),
            ]
        if intent == "explainability":
            return [
                KbRoutePlanStep(
                    tool="kb.search",
                    purpose="Retrieve relevant results and target URIs to explain.",
                ),
                KbRoutePlanStep(
                    tool="kb.explain",
                    purpose="Explain why selected results are relevant.",
                    when="after selecting URIs from search results",
                ),
            ]
        return [
            KbRoutePlanStep(
                tool="kb.search",
                purpose="Retrieve factual evidence and citations for the query.",
            )
        ]

    @mcp.tool(name="kb.health")
    def kb_health(ctx: FastContext | None = None) -> KbHealthOutput:
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
            tools=list(REGISTERED_TOOLS),
            resources=list(REGISTERED_RESOURCES),
            prompts=list(REGISTERED_PROMPTS),
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
            meta={"policy_version": POLICY_VERSION},
        )

    @mcp.tool(name="kb.route")
    def kb_route(payload: KbRouteInput, ctx: FastContext | None = None) -> KbRouteOutput:
        t0 = perf_counter()
        auth = deps.auth.resolve_identity(
            request=_request_from_ctx(ctx),
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
                    "tool": "kb.memory.upsert",
                    "requires_citations": True,
                    "requires_confidence_threshold": True,
                },
                "prompts_optional": True,
            },
        )
        deps.metrics.inc("tool.kb.route.calls")
        latency_ms = int((perf_counter() - t0) * 1000)
        out.meta = {"latency_ms": latency_ms, "policy_version": POLICY_VERSION}
        deps.metrics.observe("tool.kb.route.latency_ms", latency_ms)
        audit_tool(
            auth=auth,
            tool="kb.route",
            params=payload.model_dump(),
            result_count=len(out.recommended_tools),
            latency_ms=latency_ms,
            acl_decision="n/a",
        )
        return out

    @mcp.tool(name="kb.search")
    def kb_search(payload: KbSearchInput, ctx: FastContext | None = None) -> KbSearchOutput:
        request_id = ensure_request_id()
        t0 = perf_counter()

        auth = resolve_identity(payload.filters.acl.model_dump(), ctx)
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
            "tool.kb.search",
            attributes={
                "tool.name": "kb.search",
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
                    "updated_after": _normalize_datetime_utc(acl_filters.get("updated_after")),
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

        deps.metrics.inc("tool.kb.search.calls")
        latency_ms = int((perf_counter() - t0) * 1000)
        output.meta = {"latency_ms": latency_ms, "request_id": request_id}
        deps.metrics.observe("tool.kb.search.latency_ms", latency_ms)
        for stage, value_ms in debug.latency_ms.items():
            deps.metrics.observe("retrieval.stage.latency_ms", value_ms, labels={"stage": stage})
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
        deps.metrics.inc("tool.kb.graph_expand.calls")
        latency_ms = int((perf_counter() - t0) * 1000)
        out.meta = {"latency_ms": latency_ms}
        deps.metrics.observe("tool.kb.graph_expand.latency_ms", latency_ms)
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
        deps.metrics.inc("tool.kb.explain.calls")
        latency_ms = int((perf_counter() - t0) * 1000)
        deps.metrics.observe("tool.kb.explain.latency_ms", latency_ms)
        audit_tool(
            auth=auth,
            tool="kb.explain",
            params=payload.model_dump(),
            result_count=len(explanations),
            latency_ms=latency_ms,
            acl_decision="applied",
        )
        return KbExplainOutput(explanations=explanations, meta={"latency_ms": latency_ms})

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
        deps.metrics.observe("tool.kb.memory.upsert.latency_ms", latency_ms)
        audit_tool(
            auth=auth,
            tool="kb.memory.upsert",
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
        deps.metrics.observe("tool.kb.memory.search.latency_ms", latency_ms)
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
            ],
            meta={"latency_ms": latency_ms},
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
        deps.metrics.observe("tool.kb.memory.delete.latency_ms", latency_ms)
        audit_tool(
            auth=auth,
            tool="kb.memory.delete",
            params=payload.model_dump(),
            result_count=deleted,
            latency_ms=latency_ms,
            acl_decision="applied",
        )
        return KbMemoryDeleteOutput(deleted_count=deleted, meta={"latency_ms": latency_ms})

    @mcp.tool(name="kb.ingest.filesystem")
    def kb_ingest_filesystem(
        root_path: str,
        workspace_id: str,
        acl_subject: str,
        dry_run: bool = False,
        ctx: FastContext | None = None,
    ) -> KbIngestOutput:
        t0 = perf_counter()
        auth = resolve_identity(_legacy_acl(workspace_id=workspace_id, subject=acl_subject), ctx)
        allowed, resolved_root = _path_allowed(root_path, cfg.ingest_allowed_roots)
        if not allowed:
            latency_ms = int((perf_counter() - t0) * 1000)
            audit_tool(
                auth=auth,
                tool="kb.ingest.filesystem",
                params={
                    "root_path": root_path,
                    "workspace_id": workspace_id,
                    "acl_subject": acl_subject,
                    "dry_run": dry_run,
                },
                result_count=0,
                latency_ms=latency_ms,
                acl_decision="denied",
            )
            return KbIngestOutput(
                ok=False,
                error_code="PERMISSION_DENIED",
                error_detail=f"Ingestion root is outside KB_INGEST_ALLOWED_ROOTS: {resolved_root}",
                dry_run=dry_run,
                meta={
                    "latency_ms": latency_ms,
                    "resolved_root": resolved_root,
                    "allowed_roots": list(cfg.ingest_allowed_roots),
                },
            )
        result = deps.ingestion.ingest_filesystem(
            root=root_path,
            workspace_id=auth.ctx.workspace_id,
            acl_allow=[auth.ctx.subject],
            dry_run=dry_run,
        )
        deps.metrics.inc("tool.kb.ingest.filesystem.calls")
        latency_ms = int((perf_counter() - t0) * 1000)
        deps.metrics.observe("tool.kb.ingest.filesystem.latency_ms", latency_ms)
        audit_tool(
            auth=auth,
            tool="kb.ingest.filesystem",
            params={
                "root_path": root_path,
                "workspace_id": workspace_id,
                "acl_subject": acl_subject,
                "dry_run": dry_run,
            },
            result_count=_result_int(result, "created") + _result_int(result, "updated"),
            latency_ms=latency_ms,
            acl_decision="applied",
        )
        return KbIngestOutput(
            created=_result_int(result, "created"),
            updated=_result_int(result, "updated"),
            skipped=_result_int(result, "skipped"),
            dry_run=bool(result.get("dry_run", dry_run)),
            meta={"latency_ms": latency_ms, "resolved_root": resolved_root},
        )

    @mcp.tool(name="kb.ingest.git_diff")
    def kb_ingest_git_diff(
        repo_root: str,
        workspace_id: str,
        acl_subject: str,
        since_ref: str = "HEAD~1",
        dry_run: bool = False,
        ctx: FastContext | None = None,
    ) -> KbIngestOutput:
        t0 = perf_counter()
        auth = resolve_identity(_legacy_acl(workspace_id=workspace_id, subject=acl_subject), ctx)
        allowed, resolved_root = _path_allowed(repo_root, cfg.ingest_allowed_roots)
        if not allowed:
            latency_ms = int((perf_counter() - t0) * 1000)
            audit_tool(
                auth=auth,
                tool="kb.ingest.git_diff",
                params={
                    "repo_root": repo_root,
                    "workspace_id": workspace_id,
                    "acl_subject": acl_subject,
                    "since_ref": since_ref,
                    "dry_run": dry_run,
                },
                result_count=0,
                latency_ms=latency_ms,
                acl_decision="denied",
            )
            return KbIngestOutput(
                ok=False,
                error_code="PERMISSION_DENIED",
                error_detail=f"Ingestion root is outside KB_INGEST_ALLOWED_ROOTS: {resolved_root}",
                dry_run=dry_run,
                meta={
                    "latency_ms": latency_ms,
                    "resolved_root": resolved_root,
                    "allowed_roots": list(cfg.ingest_allowed_roots),
                },
            )
        result = deps.ingestion.ingest_git_diff(
            root=repo_root,
            workspace_id=auth.ctx.workspace_id,
            acl_allow=[auth.ctx.subject],
            since_ref=since_ref,
            dry_run=dry_run,
        )
        deps.metrics.inc("tool.kb.ingest.git_diff.calls")
        latency_ms = int((perf_counter() - t0) * 1000)
        deps.metrics.observe("tool.kb.ingest.git_diff.latency_ms", latency_ms)
        audit_tool(
            auth=auth,
            tool="kb.ingest.git_diff",
            params={
                "repo_root": repo_root,
                "workspace_id": workspace_id,
                "acl_subject": acl_subject,
                "since_ref": since_ref,
                "dry_run": dry_run,
            },
            result_count=_result_int(result, "created") + _result_int(result, "updated"),
            latency_ms=latency_ms,
            acl_decision="applied",
        )
        return KbIngestOutput(
            created=_result_int(result, "created"),
            updated=_result_int(result, "updated"),
            skipped=_result_int(result, "skipped"),
            dry_run=bool(result.get("dry_run", dry_run)),
            meta={"latency_ms": latency_ms, "resolved_root": resolved_root, "since_ref": since_ref},
        )

    @mcp.resource("kb://doc/{doc_id}")
    def resource_doc(doc_id: str, ctx: FastContext | None = None) -> dict[str, Any]:
        uri = f"kb://doc/{doc_id}"
        doc = deps.metadata.get_doc(uri)
        if doc is None:
            return _contract_error(
                uri=uri,
                legacy_error="not_found",
                error_code="NOT_FOUND",
                detail="Document resource was not found.",
            )
        auth = deps.auth.resolve_identity(
            request=_request_from_ctx(ctx),
            payload_acl=None,
            allow_legacy_payload=False,
        )
        if not _resource_allowed(deps=deps, auth_ctx=auth.ctx, data=doc):
            return _contract_error(
                uri=uri,
                legacy_error="forbidden",
                error_code="PERMISSION_DENIED",
                detail="Bearer identity cannot read this document resource.",
            )
        out = dict(doc)
        if "text" in out:
            out["text"] = deps.redact.redact(str(out["text"]))
        return _contract_ok(out)

    @mcp.resource("kb://chunk/{chunk_id}")
    def resource_chunk(chunk_id: str, ctx: FastContext | None = None) -> dict[str, Any]:
        uri = f"kb://chunk/{chunk_id}"
        chunk = deps.metadata.get_chunk(uri)
        if chunk is None:
            return _contract_error(
                uri=uri,
                legacy_error="not_found",
                error_code="NOT_FOUND",
                detail="Chunk resource was not found.",
            )
        auth = deps.auth.resolve_identity(
            request=_request_from_ctx(ctx),
            payload_acl=None,
            allow_legacy_payload=False,
        )
        if not _resource_allowed(deps=deps, auth_ctx=auth.ctx, data=chunk):
            return _contract_error(
                uri=uri,
                legacy_error="forbidden",
                error_code="PERMISSION_DENIED",
                detail="Bearer identity cannot read this chunk resource.",
            )
        out = dict(chunk)
        out["text"] = deps.redact.redact(str(out.get("text", "")))
        return _contract_ok(out)

    @mcp.resource("kb://entity/{entity_id}")
    def resource_entity(entity_id: str, ctx: FastContext | None = None) -> dict[str, Any]:
        uri = f"kb://entity/{entity_id}"
        entity = deps.metadata.get_entity(uri)
        if entity is None:
            return _contract_ok({"uri": uri, "type": "Entity", "name": entity_id, "links": []})
        auth = deps.auth.resolve_identity(
            request=_request_from_ctx(ctx),
            payload_acl=None,
            allow_legacy_payload=False,
        )
        if not _resource_allowed(deps=deps, auth_ctx=auth.ctx, data=entity):
            return _contract_error(
                uri=uri,
                legacy_error="forbidden",
                error_code="PERMISSION_DENIED",
                detail="Bearer identity cannot read this entity resource.",
            )
        return _contract_ok(entity)

    @mcp.resource("kb://memory/{memory_id}")
    def resource_memory(memory_id: str, ctx: FastContext | None = None) -> dict[str, Any]:
        uri = f"kb://memory/{memory_id}"
        memory = deps.metadata.get_memory(uri)
        if memory is None:
            return _contract_error(
                uri=uri,
                legacy_error="not_found",
                error_code="NOT_FOUND",
                detail="Memory resource was not found.",
            )
        auth = deps.auth.resolve_identity(
            request=_request_from_ctx(ctx),
            payload_acl=None,
            allow_legacy_payload=False,
        )
        if not _resource_allowed(deps=deps, auth_ctx=auth.ctx, data=memory):
            return _contract_error(
                uri=uri,
                legacy_error="forbidden",
                error_code="PERMISSION_DENIED",
                detail="Bearer identity cannot read this memory resource.",
            )
        out = dict(memory)
        out["text"] = deps.redact.redact(str(out.get("text", "")))
        return _contract_ok(out)

    @mcp.resource("kb://policy/tool-selection")
    def resource_tool_selection_policy() -> dict[str, Any]:
        return _contract_ok({
            "version": POLICY_VERSION,
            "intent_catalog": [
                "fact_lookup",
                "relation_impact",
                "explainability",
                "memory_context",
                "memory_delete",
            ],
            "priority_tools": [
                "kb.route",
                "kb.memory.search",
                "kb.search",
                "kb.graph_expand",
                "kb.explain",
            ],
            "router_tool": "kb.route",
            "memory_write_constraints": {
                "tool": "kb.memory.upsert",
                "requires_citations": True,
                "requires_confidence_threshold": True,
            },
            "fallback_policy": "When graph backend is unavailable, return vector-only evidence with explicit limitation.",
        })

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
