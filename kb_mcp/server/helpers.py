from __future__ import annotations

from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, TypeVar, cast
from mcp.server.fastmcp import Context

if TYPE_CHECKING:
    FastContext = Context[Any, Any, Any]
else:
    FastContext = Context

F = TypeVar("F", bound=Callable[..., Any])


def request_from_ctx(ctx: FastContext | None) -> Any | None:
    if ctx is None:
        return None
    try:
        req_ctx = ctx.request_context
    except Exception:
        return None
    return req_ctx.request if req_ctx is not None else None


def legacy_acl(*, workspace_id: str, subject: str) -> dict[str, Any]:
    return {
        "workspace_id": workspace_id,
        "subject": subject,
        "roles": [],
        "jwt_bearer": None,
    }


def resource_allowed(*, deps: Any, auth_ctx: Any, data: dict[str, Any]) -> bool:
    workspace_id = str(data.get("workspace_id", "")).strip()
    if workspace_id and workspace_id != auth_ctx.workspace_id:
        return False
    acl_allow_raw = data.get("acl_allow")
    acl_allow = [str(v) for v in acl_allow_raw] if isinstance(acl_allow_raw, list) else None
    return bool(deps.acl.can_read(ctx=auth_ctx, acl_allow=acl_allow))


def normalize_datetime_utc(value: object) -> str | None:
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


def resource_server_url(*, host: str, port: int) -> str:
    normalized = host.strip() or "127.0.0.1"
    if normalized in {"0.0.0.0", "::"}:
        normalized = "127.0.0.1"
    if ":" in normalized and not normalized.startswith("["):
        normalized = f"[{normalized}]"
    return f"http://{normalized}:{port}"


def contract_ok(data: dict[str, Any]) -> dict[str, Any]:
    out = dict(data)
    out.setdefault("ok", True)
    out.setdefault("error_code", None)
    out.setdefault("error_detail", None)
    out.setdefault("meta", {})
    return out


def contract_error(*, uri: str, legacy_error: str, error_code: str, detail: str) -> dict[str, Any]:
    return {
        "error": legacy_error,
        "uri": uri,
        "ok": False,
        "error_code": error_code,
        "error_detail": detail,
        "meta": {},
    }


def result_int(result: dict[str, object], key: str) -> int:
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


def path_allowed(path: str, allowed_roots: tuple[str, ...]) -> tuple[bool, str]:
    resolved = Path(path).expanduser().resolve()
    if not allowed_roots:
        return True, str(resolved)
    for root in allowed_roots:
        allowed = Path(root).expanduser().resolve()
        if resolved == allowed or allowed in resolved.parents:
            return True, str(resolved)
    return False, str(resolved)


def resolve_identity(deps: Any, payload_acl: dict[str, Any] | None, ctx: FastContext | None) -> Any:
    return deps.auth.resolve_identity(
        request=request_from_ctx(ctx),
        payload_acl=payload_acl,
        allow_legacy_payload=True,
    )


def audit_tool(
    deps: Any,
    *,
    auth: Any,
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


def with_middlewares(name: str, deps: Any) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        from kb_mcp.server.schemas import ContractFields

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            cfg = deps.config

            # Find Context 'ctx' in positional or keyword arguments
            ctx = None
            for arg in args:
                if hasattr(arg, "request_context"):
                    ctx = arg
                    break
            if ctx is None:
                ctx = kwargs.get("ctx")

            # Extract subject and workspace_id
            subject = "anonymous"
            workspace_id = "default"

            # Try to get from kwargs payload
            payload = kwargs.get("payload")
            if payload is not None:
                if hasattr(payload, "workspace_id"):
                    workspace_id = str(getattr(payload, "workspace_id", "default"))
                    subject = str(getattr(payload, "subject", "anonymous"))
                elif isinstance(payload, dict):
                    workspace_id = str(payload.get("workspace_id", "default"))
                    subject = str(payload.get("subject", "anonymous"))
            elif "workspace_id" in kwargs:
                workspace_id = str(kwargs.get("workspace_id", "default"))
                subject = str(kwargs.get("acl_subject", "anonymous"))
            elif ctx is not None:
                try:
                    auth = deps.auth.resolve_identity(
                        request=request_from_ctx(ctx),
                        payload_acl=None,
                        allow_legacy_payload=True,
                    )
                    subject = auth.ctx.subject
                    workspace_id = auth.ctx.workspace_id
                except Exception:
                    pass

            # 1. Circuit Breaker
            if cfg.circuit_breaker_enabled:
                if not deps.circuit_breaker.allow_request():
                    from typing import get_type_hints
                    ret_type = get_type_hints(func).get("return", ContractFields)
                    return ret_type(
                        ok=False,
                        error_code="UPSTREAM_UNAVAILABLE",
                        error_detail="Circuit breaker is OPEN. Upstream dependency is unavailable.",
                        recoverable=True,
                        next_action="retry after recovery timeout",
                    )

            # 2. Rate Limiting
            if cfg.rate_limit_enabled:
                if not deps.rate_limiter.is_allowed(subject, workspace_id, name):
                    from typing import get_type_hints
                    ret_type = get_type_hints(func).get("return", ContractFields)
                    return ret_type(
                        ok=False,
                        error_code="RATE_LIMITED",
                        error_detail=f"Rate limit exceeded for {subject} on workspace {workspace_id} for tool {name}.",
                        recoverable=True,
                        next_action="backoff and retry",
                    )

            # 3. Execution
            try:
                result = func(*args, **kwargs)
                if cfg.circuit_breaker_enabled:
                    deps.circuit_breaker.record_success()
                return result
            except Exception as e:
                if cfg.circuit_breaker_enabled:
                    deps.circuit_breaker.record_failure()
                raise e
        return cast(F, wrapper)
    return decorator
