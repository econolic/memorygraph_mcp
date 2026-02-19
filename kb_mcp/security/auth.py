from __future__ import annotations

from dataclasses import dataclass

import jwt

from kb_mcp.config import AppConfig
from kb_mcp.security.acl import AccessContext


@dataclass(frozen=True)
class AuthResult:
    ok: bool
    ctx: AccessContext | None
    error: str | None = None


class JwtAuthService:
    def __init__(self, cfg: AppConfig) -> None:
        self._cfg = cfg

    def parse_bearer(self, token: str) -> AuthResult:
        try:
            payload = jwt.decode(
                token,
                key=self._cfg.jwt_secret,
                algorithms=list(self._cfg.jwt_algorithms),
            )
        except Exception as exc:
            return AuthResult(ok=False, ctx=None, error=str(exc))

        subject = str(payload.get("sub", ""))
        workspace_id = str(payload.get("workspace_id", ""))
        roles_raw = payload.get("roles", [])
        roles = tuple(str(role) for role in roles_raw) if isinstance(roles_raw, list) else tuple()
        if not subject or not workspace_id:
            return AuthResult(ok=False, ctx=None, error="missing_sub_or_workspace")

        return AuthResult(
            ok=True,
            ctx=AccessContext(subject=subject, roles=roles, workspace_id=workspace_id),
        )
