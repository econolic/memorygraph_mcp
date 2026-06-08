from __future__ import annotations

from time import perf_counter
from typing import Any
from mcp.server.fastmcp import FastMCP
from kb_mcp.server.helpers import FastContext

from kb_mcp.server.schemas import KbIngestOutput
from kb_mcp.server.helpers import (
    resolve_identity,
    audit_tool,
    legacy_acl,
    path_allowed,
    result_int,
    with_middlewares,
)

def register_ingest_tools(mcp: FastMCP, deps: Any) -> None:
    cfg = deps.config

    @mcp.tool(name="kb_ingest_filesystem")
    @with_middlewares("kb_ingest_filesystem", deps)
    def kb_ingest_filesystem(
        root_path: str,
        workspace_id: str,
        acl_subject: str,
        dry_run: bool = False,
        ctx: FastContext | None = None,
    ) -> KbIngestOutput:
        """Scan and ingest all documents from a local filesystem directory root into the knowledge base."""
        t0 = perf_counter()
        auth = resolve_identity(deps, legacy_acl(workspace_id=workspace_id, subject=acl_subject), ctx)
        allowed, resolved_root = path_allowed(root_path, cfg.ingest_allowed_roots)
        if not allowed:
            latency_ms = int((perf_counter() - t0) * 1000)
            audit_tool(
                deps,
                auth=auth,
                tool="kb_ingest_filesystem",
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
        try:
            result = deps.ingestion.ingest_filesystem(
                root=root_path,
                workspace_id=auth.ctx.workspace_id,
                acl_allow=[auth.ctx.subject],
                dry_run=dry_run,
            )
        except RuntimeError as exc:
            if "already in progress" in str(exc):
                latency_ms = int((perf_counter() - t0) * 1000)
                audit_tool(
                    deps,
                    auth=auth,
                    tool="kb_ingest_filesystem",
                    params={
                        "root_path": root_path,
                        "workspace_id": workspace_id,
                        "acl_subject": acl_subject,
                        "dry_run": dry_run,
                    },
                    result_count=0,
                    latency_ms=latency_ms,
                    acl_decision="applied",
                )
                return KbIngestOutput(
                    ok=False,
                    error_code="CONFLICT",
                    error_detail=str(exc),
                    dry_run=dry_run,
                    meta={"latency_ms": latency_ms, "resolved_root": resolved_root},
                )
            raise
        deps.metrics.inc("tool.kb_ingest_filesystem.calls")
        latency_ms = int((perf_counter() - t0) * 1000)
        deps.metrics.observe("tool.kb_ingest_filesystem.latency_ms", latency_ms)
        audit_tool(
            deps,
            auth=auth,
            tool="kb_ingest_filesystem",
            params={
                "root_path": root_path,
                "workspace_id": workspace_id,
                "acl_subject": acl_subject,
                "dry_run": dry_run,
            },
            result_count=result_int(result, "created") + result_int(result, "updated"),
            latency_ms=latency_ms,
            acl_decision="applied",
        )
        return KbIngestOutput(
            created=result_int(result, "created"),
            updated=result_int(result, "updated"),
            skipped=result_int(result, "skipped"),
            dry_run=bool(result.get("dry_run", dry_run)),
            meta={"latency_ms": latency_ms, "resolved_root": resolved_root},
        )

    @mcp.tool(name="kb_ingest_git_diff")
    @with_middlewares("kb_ingest_git_diff", deps)
    def kb_ingest_git_diff(
        repo_root: str,
        workspace_id: str,
        acl_subject: str,
        since_ref: str = "HEAD~1",
        dry_run: bool = False,
        ctx: FastContext | None = None,
    ) -> KbIngestOutput:
        """Scan and ingest changes between Git commits/references in a local repository root."""
        t0 = perf_counter()
        auth = resolve_identity(deps, legacy_acl(workspace_id=workspace_id, subject=acl_subject), ctx)
        allowed, resolved_root = path_allowed(repo_root, cfg.ingest_allowed_roots)
        if not allowed:
            latency_ms = int((perf_counter() - t0) * 1000)
            audit_tool(
                deps,
                auth=auth,
                tool="kb_ingest_git_diff",
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
        try:
            result = deps.ingestion.ingest_git_diff(
                root=repo_root,
                workspace_id=auth.ctx.workspace_id,
                acl_allow=[auth.ctx.subject],
                since_ref=since_ref,
                dry_run=dry_run,
            )
        except RuntimeError as exc:
            if "already in progress" in str(exc):
                latency_ms = int((perf_counter() - t0) * 1000)
                audit_tool(
                    deps,
                    auth=auth,
                    tool="kb_ingest_git_diff",
                    params={
                        "repo_root": repo_root,
                        "workspace_id": workspace_id,
                        "acl_subject": acl_subject,
                        "since_ref": since_ref,
                        "dry_run": dry_run,
                    },
                    result_count=0,
                    latency_ms=latency_ms,
                    acl_decision="applied",
                )
                return KbIngestOutput(
                    ok=False,
                    error_code="CONFLICT",
                    error_detail=str(exc),
                    dry_run=dry_run,
                    meta={"latency_ms": latency_ms, "resolved_root": resolved_root, "since_ref": since_ref},
                )
            raise
        deps.metrics.inc("tool.kb_ingest_git_diff.calls")
        latency_ms = int((perf_counter() - t0) * 1000)
        deps.metrics.observe("tool.kb_ingest_git_diff.latency_ms", latency_ms)
        audit_tool(
            deps,
            auth=auth,
            tool="kb_ingest_git_diff",
            params={
                "repo_root": repo_root,
                "workspace_id": workspace_id,
                "acl_subject": acl_subject,
                "since_ref": since_ref,
                "dry_run": dry_run,
            },
            result_count=result_int(result, "created") + result_int(result, "updated"),
            latency_ms=latency_ms,
            acl_decision="applied",
        )
        return KbIngestOutput(
            created=result_int(result, "created"),
            updated=result_int(result, "updated"),
            skipped=result_int(result, "skipped"),
            dry_run=bool(result.get("dry_run", dry_run)),
            meta={"latency_ms": latency_ms, "resolved_root": resolved_root, "since_ref": since_ref},
        )
