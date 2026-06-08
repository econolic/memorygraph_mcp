from typing import Any
from fastapi import FastAPI, Depends, Request
from kb_mcp.bootstrap import build_deps, AppDeps
from kb_mcp.server.schemas import (
    KbSearchInput, KbSearchOutput,
    KbGraphExpandInput, KbGraphExpandOutput,
    KbExplainInput, KbExplainOutput,
    KbMemoryUpsertInput, KbMemoryUpsertOutput,
    KbMemorySearchInput, KbMemorySearchOutput,
    KbMemoryDeleteInput, KbMemoryDeleteOutput,
    KbIngestOutput, KbRouteInput, KbRouteOutput,
    KbHealthOutput
)
from contextlib import asynccontextmanager
from time import perf_counter
from kb_mcp.server.helpers import resolve_identity, legacy_acl, path_allowed, result_int
from kb_mcp.retrieval.router import QueryRouter, POLICY_VERSION
from kb_mcp.retrieval.rerank import RerankConfig
from kb_mcp.server.schemas import SearchResult, Citation, EntityRef, MemoryHit
from kb_mcp.observability.tracing import ensure_request_id
from pydantic import BaseModel

deps: AppDeps | None = None
from typing import Any, AsyncGenerator

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global deps
    deps = build_deps()
    yield

app = FastAPI(
    title="Hybrid KB MCP Server - Swagger Documentation",
    description="REST endpoints that execute the core logic of the MCP tools. Note: these endpoints bypass the JSON-RPC/SSE MCP transport and interact directly with the backend services for documentation and HTTP-based integration.",
    version="0.1.0",
    lifespan=lifespan
)

def get_deps() -> AppDeps:
    if deps is None:
        raise RuntimeError("Dependencies not initialized")
    return deps

@app.post("/tools/kb.search", response_model=KbSearchOutput, tags=["Search"])
async def kb_search(payload: KbSearchInput, request: Request, deps: AppDeps = Depends(get_deps)) -> KbSearchOutput:
    """Search the hybrid knowledge base (vector + graph)."""
    request_id = ensure_request_id()
    t0 = perf_counter()
    router = QueryRouter()
    
    auth = resolve_identity(deps, payload.filters.acl.model_dump(), None)
    acl_filters = deps.acl.apply_filters(ctx=auth.ctx, filters=payload.filters.model_dump())
    search_workspace = auth.ctx.workspace_id
    acl_filters["workspace_id"] = search_workspace
    acl_filters["graph_enforce_object_acl"] = deps.config.graph_enforce_object_acl

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
        enabled=payload.rerank.enabled, provider=payload.rerank.provider, top_n=payload.rerank.top_n
    )

    depth = payload.graph.expand_depth if routed.mode != "vector" else 0
    edge_types = payload.graph.edge_types if routed.mode != "vector" else []

    items, debug = deps.retriever.search(
        query=payload.query,
        top_k=min(payload.top_k, deps.config.max_top_k),
        filters=acl_filters,
        depth=min(depth, deps.config.max_expand_depth),
        edge_types=edge_types,
        max_nodes=payload.graph.max_nodes,
        memory_bonus_by_uri=memory_bonus_by_uri,
        rerank=rerank_cfg,
    )

    results = []
    for item in items:
        ev = deps.evidence.build(uri=item.uri, score=item.score, breakdown=item.score_breakdown)
        results.append(
            SearchResult(
                uri=ev.uri, title=ev.title, snippet=deps.redact.redact(ev.snippet),
                score=ev.score, score_breakdown=ev.score_breakdown,
                citations=[Citation.model_validate(c) for c in ev.citations],
                entities=[EntityRef.model_validate(e) for e in ev.entities],
            )
        )

    acl_roles_raw = acl_filters.get("acl_roles", [])
    acl_roles = [str(role) for role in acl_roles_raw] if isinstance(acl_roles_raw, list) else []

    output = KbSearchOutput(
        query_id=request_id,
        results=results,
        memory_hits=[
            MemoryHit(uri=h.uri, score=h.score, text=deps.redact.redact(h.text), citations=h.citations)
            for h in memory_hits
        ],
        decision_trace={
            "request_id": request_id, "mode": routed.mode, "route_reason": routed.reason,
            "intent": routed.intent, "recommended_tools": list(routed.recommended_tools),
            "policy_version": POLICY_VERSION, "auth_mode": auth.auth_mode,
            "identity_source": auth.identity_source, "rerank_provider": payload.rerank.provider,
            "fusion_mode": debug.fusion_mode,
        },
        debug={
            "latency_ms": debug.latency_ms, "fallback_mode": debug.fallback_mode,
            "fallback_reason": debug.fallback_reason, "filters_applied": True,
            "filters_effective": {
                "workspace_id": str(acl_filters.get("workspace_id", "")),
                "acl_subject": str(acl_filters.get("acl_subject", "")),
                "acl_roles": acl_roles,
            },
            "graph_acl_enforced": deps.config.graph_enforce_object_acl,
            "fusion_mode": debug.fusion_mode, "graph_seed_count": debug.graph_seed_count,
            "graph_node_count": debug.graph_node_count,
        },
    )
    latency_ms = int((perf_counter() - t0) * 1000)
    output.meta = {"latency_ms": latency_ms, "request_id": request_id}
    return output

@app.post("/tools/kb.graph_expand", response_model=KbGraphExpandOutput, tags=["Search"])
async def kb_graph_expand(payload: KbGraphExpandInput, deps: AppDeps = Depends(get_deps)) -> KbGraphExpandOutput:
    """Expand the knowledge graph starting from specific seed entities."""
    t0 = perf_counter()
    auth = resolve_identity(deps, legacy_acl(workspace_id=payload.workspace_id, subject=payload.subject), None)
    filters: dict[str, object] = {
        "workspace_id": auth.ctx.workspace_id,
        "acl_subject": auth.ctx.subject,
        "acl_roles": list(auth.ctx.roles),
        "graph_enforce_object_acl": deps.config.graph_enforce_object_acl,
    }
    nodes, edges = deps.graph_store.expand(
        seed_uris=payload.seed_entities,
        depth=payload.depth,
        edge_types=payload.edge_types,
        max_nodes=payload.max_nodes,
        filters=filters,
    )
    paths = [[edge.src, edge.rel, edge.dst] for edge in edges]
    latency_ms = int((perf_counter() - t0) * 1000)
    return KbGraphExpandOutput(
        nodes=[{"uri": n.uri, "type": n.type, "name": n.name, **n.properties} for n in nodes],
        edges=[{"src": e.src, "rel": e.rel, "dst": e.dst} for e in edges],
        paths=paths,
        meta={"latency_ms": latency_ms}
    )

@app.post("/tools/kb.explain", response_model=KbExplainOutput, tags=["Search"])
async def kb_explain(payload: KbExplainInput, deps: AppDeps = Depends(get_deps)) -> KbExplainOutput:
    """Explain how specific URIs were discovered via graph paths or vector similarity."""
    t0 = perf_counter()
    auth = resolve_identity(deps, legacy_acl(workspace_id=payload.workspace_id, subject=payload.subject), None)
    filters: dict[str, object] = {
        "workspace_id": auth.ctx.workspace_id,
        "acl_subject": auth.ctx.subject,
        "acl_roles": list(auth.ctx.roles),
        "graph_enforce_object_acl": deps.config.graph_enforce_object_acl,
    }
    explanations: list[dict[str, Any]] = []
    for uri in payload.uris:
        graph_reasons = deps.graph_store.explain_uri(uri=uri, filters=filters)
        reasons = [{"type": "graph", "detail": reason} for reason in graph_reasons]
        reasons.insert(0, {"type": "vector", "detail": "score derived from vector similarity + fusion + rerank"})
        explanations.append({"uri": uri, "reasons": reasons})
    latency_ms = int((perf_counter() - t0) * 1000)
    return KbExplainOutput(explanations=explanations, meta={"latency_ms": latency_ms})

@app.post("/tools/kb.memory.upsert", response_model=KbMemoryUpsertOutput, tags=["Memory"])
async def kb_memory_upsert(payload: KbMemoryUpsertInput, deps: AppDeps = Depends(get_deps)) -> KbMemoryUpsertOutput:
    """Store memories associated with a workspace/subject."""
    t0 = perf_counter()
    auth = resolve_identity(deps, legacy_acl(workspace_id=payload.workspace_id, subject=payload.subject), None)
    stored_ids, report = deps.memory.upsert(
        workspace_id=auth.ctx.workspace_id,
        subject=auth.ctx.subject,
        session_id=payload.session_id,
        items=[item.model_dump() for item in payload.items],
        idempotency_key=payload.idempotency_key,
    )
    latency_ms = int((perf_counter() - t0) * 1000)
    return KbMemoryUpsertOutput(
        stored_ids=stored_ids, validation_report=report, meta={"latency_ms": latency_ms}
    )

@app.post("/tools/kb.memory.search", response_model=KbMemorySearchOutput, tags=["Memory"])
async def kb_memory_search(payload: KbMemorySearchInput, deps: AppDeps = Depends(get_deps)) -> KbMemorySearchOutput:
    """Search previously stored memories."""
    t0 = perf_counter()
    auth = resolve_identity(deps, legacy_acl(workspace_id=payload.workspace_id, subject=payload.subject), None)
    hits = deps.memory.search(
        query=payload.query,
        workspace_id=auth.ctx.workspace_id,
        subject=auth.ctx.subject,
        top_k=payload.top_k,
    )
    latency_ms = int((perf_counter() - t0) * 1000)
    return KbMemorySearchOutput(
        results=[MemoryHit(uri=hit.uri, score=hit.score, text=deps.redact.redact(hit.text), citations=hit.citations) for hit in hits],
        meta={"latency_ms": latency_ms},
    )

@app.post("/tools/kb.memory.delete", response_model=KbMemoryDeleteOutput, tags=["Memory"])
async def kb_memory_delete(payload: KbMemoryDeleteInput, deps: AppDeps = Depends(get_deps)) -> KbMemoryDeleteOutput:
    """Delete memories via a 2-step destructive confirmation token."""
    t0 = perf_counter()
    auth = resolve_identity(deps, legacy_acl(workspace_id=payload.workspace_id, subject=payload.subject), None)

    if not payload.confirmation_token:
        items = deps.metadata.list_memory(workspace_id=auth.ctx.workspace_id, subject=auth.ctx.subject) if payload.all_for_subject else []
        if not payload.all_for_subject:
            for mid in payload.ids:
                m_uri = f"kb://memory/{mid}"
                m_item = deps.metadata.get_memory(m_uri)
                if m_item and m_item.get("workspace_id") == auth.ctx.workspace_id and m_item.get("subject") == auth.ctx.subject:
                    items.append(m_item)
        preview_items = [{"id": str(item.get("uri", "")).split("/")[-1], "text": str(item.get("text", ""))[:100]} for item in items]
        gate_data = {
            "workspace_id": auth.ctx.workspace_id, "subject": auth.ctx.subject,
            "ids": payload.ids, "all_for_subject": payload.all_for_subject,
        }
        token = deps.confirmation.generate_token(gate_data)
        latency_ms = int((perf_counter() - t0) * 1000)
        return KbMemoryDeleteOutput(
            ok=False, error_code="BUSINESS_RULE_VIOLATION",
            error_detail="This operation is destructive and requires confirmation.",
            recoverable=True, next_action="provide confirmation_token", deleted_count=0,
            meta={"confirmation_token": token, "preview": {"count": len(preview_items), "items": preview_items}, "latency_ms": latency_ms}
        )
    validated_gate = deps.confirmation.validate_and_invalidate(payload.confirmation_token)
    if not validated_gate:
        return KbMemoryDeleteOutput(ok=False, error_code="VALIDATION_ERROR", error_detail="Invalid or expired token.", deleted_count=0)
    
    deleted = deps.memory.delete(workspace_id=auth.ctx.workspace_id, subject=auth.ctx.subject, ids=validated_gate["ids"], all_for_subject=validated_gate["all_for_subject"])
    latency_ms = int((perf_counter() - t0) * 1000)
    return KbMemoryDeleteOutput(deleted_count=deleted, meta={"latency_ms": latency_ms})

class FilesystemIngestInput(BaseModel):
    root_path: str
    workspace_id: str
    acl_subject: str
    dry_run: bool = False

@app.post("/tools/kb.ingest.filesystem", response_model=KbIngestOutput, tags=["Ingestion"])
async def kb_ingest_filesystem(payload: FilesystemIngestInput, deps: AppDeps = Depends(get_deps)) -> KbIngestOutput:
    """Ingest markdown and text files from the local filesystem."""
    t0 = perf_counter()
    auth = resolve_identity(deps, legacy_acl(workspace_id=payload.workspace_id, subject=payload.acl_subject), None)
    allowed, resolved_root = path_allowed(payload.root_path, deps.config.ingest_allowed_roots)
    if not allowed:
        return KbIngestOutput(ok=False, error_code="PERMISSION_DENIED", error_detail="Outside allowed roots", dry_run=payload.dry_run)
    try:
        result = deps.ingestion.ingest_filesystem(
            root=payload.root_path, workspace_id=auth.ctx.workspace_id,
            acl_allow=[auth.ctx.subject], dry_run=payload.dry_run,
        )
    except RuntimeError as exc:
        if "already in progress" in str(exc):
            return KbIngestOutput(
                ok=False,
                error_code="CONFLICT",
                error_detail=str(exc),
                dry_run=payload.dry_run,
                meta={"latency_ms": int((perf_counter() - t0) * 1000), "resolved_root": resolved_root},
            )
        raise
    latency_ms = int((perf_counter() - t0) * 1000)
    meta: dict[str, Any] = {"latency_ms": latency_ms, "resolved_root": resolved_root}
    return KbIngestOutput(
        created=result_int(result, "created"), updated=result_int(result, "updated"), skipped=result_int(result, "skipped"),
        dry_run=bool(result.get("dry_run", payload.dry_run)), meta=meta
    )

class GitIngestInput(BaseModel):
    repo_root: str
    workspace_id: str
    acl_subject: str
    since_ref: str = "HEAD~1"
    dry_run: bool = False

@app.post("/tools/kb.ingest.git_diff", response_model=KbIngestOutput, tags=["Ingestion"])
async def kb_ingest_git_diff(payload: GitIngestInput, deps: AppDeps = Depends(get_deps)) -> KbIngestOutput:
    """Ingest new and modified files from a git repository based on a diff."""
    t0 = perf_counter()
    auth = resolve_identity(deps, legacy_acl(workspace_id=payload.workspace_id, subject=payload.acl_subject), None)
    allowed, resolved_root = path_allowed(payload.repo_root, deps.config.ingest_allowed_roots)
    if not allowed:
        return KbIngestOutput(ok=False, error_code="PERMISSION_DENIED", error_detail="Outside allowed roots", dry_run=payload.dry_run)
    try:
        result = deps.ingestion.ingest_git_diff(
            root=payload.repo_root, workspace_id=auth.ctx.workspace_id,
            acl_allow=[auth.ctx.subject], since_ref=payload.since_ref, dry_run=payload.dry_run,
        )
    except RuntimeError as exc:
        if "already in progress" in str(exc):
            return KbIngestOutput(
                ok=False,
                error_code="CONFLICT",
                error_detail=str(exc),
                dry_run=payload.dry_run,
                meta={"latency_ms": int((perf_counter() - t0) * 1000), "resolved_root": resolved_root},
            )
        raise
    latency_ms = int((perf_counter() - t0) * 1000)
    meta: dict[str, Any] = {"latency_ms": latency_ms, "resolved_root": resolved_root}
    return KbIngestOutput(
        created=result_int(result, "created"), updated=result_int(result, "updated"), skipped=result_int(result, "skipped"),
        dry_run=bool(result.get("dry_run", payload.dry_run)), meta=meta
    )

@app.post("/tools/kb.route", response_model=KbRouteOutput, tags=["System"])
async def kb_route(payload: KbRouteInput, deps: AppDeps = Depends(get_deps)) -> KbRouteOutput:
    """Evaluate a query to plan its search strategy."""
    router = QueryRouter()
    routed = router.route(payload.query, payload.requested_mode, include_memory=payload.include_memory)
    return KbRouteOutput(
        policy_version=POLICY_VERSION, intent=routed.intent, mode=routed.mode, route_reason=routed.reason,
        recommended_tools=list(routed.recommended_tools), execution_plan=[], constraints={}
    )

@app.get("/tools/kb.health", response_model=KbHealthOutput, tags=["System"])
async def kb_health(deps: AppDeps = Depends(get_deps)) -> KbHealthOutput:
    """Check the health and configuration of the KB."""
    return KbHealthOutput(
        service_name=deps.config.service_name, transport="mcp", auth_mode=deps.config.auth_mode,
        backends={"vector": deps.config.vector_backend, "graph": deps.config.graph_backend, "metadata": deps.config.metadata_backend},
        tools=[], resources=[], prompts=[]
    )
