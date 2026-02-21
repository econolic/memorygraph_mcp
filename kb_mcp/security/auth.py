from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import jwt
from mcp.server.auth.provider import TokenVerifier

from kb_mcp.config import AppConfig
from kb_mcp.security.acl import AccessContext
from kb_mcp.security.oidc import OidcJwksTokenVerifier


@dataclass(frozen=True)
class AuthResult:
    ok: bool
    ctx: AccessContext | None
    error: str | None = None


@dataclass(frozen=True)
class AuthResolution:
    ctx: AccessContext
    auth_mode: str
    identity_source: str
    deprecated_legacy_acl: bool


class JwtAuthService:
    def __init__(self, cfg: AppConfig, *, oidc_verifier: OidcJwksTokenVerifier | None = None) -> None:
        self._cfg = cfg
        self._oidc_verifier = oidc_verifier
        if self._oidc_verifier is None and cfg.auth_mode == "strict_oauth":
            self._oidc_verifier = OidcJwksTokenVerifier(
                issuer_url=cfg.oauth_issuer_url,
                audience=cfg.oauth_audience,
                jwks_url=cfg.oauth_jwks_url,
                required_scopes=cfg.oauth_required_scopes,
            )

    def oauth_token_verifier(self) -> TokenVerifier | None:
        if self._oidc_verifier is None or not self._oidc_verifier.enabled:
            return None
        return self._oidc_verifier

    def parse_bearer(self, token: str) -> AuthResult:
        if self._cfg.auth_mode == "strict_oauth":
            verifier = self._oidc_verifier
            if verifier is None or not verifier.enabled:
                return AuthResult(ok=False, ctx=None, error="oauth_not_configured")
            try:
                payload = verifier.decode_token(token)
            except Exception as exc:
                return AuthResult(ok=False, ctx=None, error=str(exc))
        else:
            try:
                payload = jwt.decode(
                    token,
                    key=self._cfg.jwt_secret,
                    algorithms=list(self._cfg.jwt_algorithms),
                )
            except Exception as exc:
                return AuthResult(ok=False, ctx=None, error=str(exc))

        subject = str(payload.get("sub", ""))
        workspace_id = str(payload.get("workspace_id", "") or payload.get("workspace", ""))
        roles_raw = payload.get("roles", [])
        if not isinstance(roles_raw, list):
            realm_access = payload.get("realm_access", {})
            if isinstance(realm_access, dict) and isinstance(realm_access.get("roles"), list):
                roles_raw = realm_access["roles"]
        roles = tuple(str(role) for role in roles_raw) if isinstance(roles_raw, list) else tuple()
        if not subject or not workspace_id:
            return AuthResult(ok=False, ctx=None, error="missing_sub_or_workspace")

        return AuthResult(
            ok=True,
            ctx=AccessContext(subject=subject, roles=roles, workspace_id=workspace_id),
        )

    def resolve_identity(
        self,
        *,
        request: Any | None,
        payload_acl: dict[str, Any] | None,
        allow_legacy_payload: bool = True,
    ) -> AuthResolution:
        auth_mode = self._cfg.auth_mode
        http_request = request is not None
        oauth_strict = auth_mode == "strict_oauth"
        header_required = auth_mode in {"strict", "strict_oauth"} and http_request

        header_token = self._extract_header_token(request)
        if header_token:
            parsed = self.parse_bearer(header_token)
            if parsed.ok and parsed.ctx is not None:
                return AuthResolution(
                    ctx=parsed.ctx,
                    auth_mode=auth_mode,
                    identity_source="authorization_header",
                    deprecated_legacy_acl=False,
                )
            if header_required:
                raise PermissionError("invalid_bearer_token")
        elif header_required:
            raise PermissionError("missing_bearer_token")

        payload_acl = payload_acl or {}
        payload_token = payload_acl.get("jwt_bearer")
        if not oauth_strict or not http_request:
            if isinstance(payload_token, str) and payload_token:
                parsed = self.parse_bearer(payload_token)
                if parsed.ok and parsed.ctx is not None:
                    return AuthResolution(
                        ctx=parsed.ctx,
                        auth_mode=auth_mode,
                        identity_source="payload_jwt",
                        deprecated_legacy_acl=False,
                    )
                if auth_mode in {"strict", "strict_oauth"} and request is not None:
                    raise PermissionError("invalid_payload_jwt")

        if allow_legacy_payload:
            legacy_subject = str(payload_acl.get("subject", "")).strip()
            legacy_workspace_id = str(payload_acl.get("workspace_id", "")).strip()
            roles_raw = payload_acl.get("roles", [])
            roles = tuple(str(role) for role in roles_raw) if isinstance(roles_raw, list) else tuple()
            if legacy_subject and legacy_workspace_id:
                if auth_mode in {"strict", "strict_oauth"} and request is not None:
                    raise PermissionError("missing_bearer_token")
                return AuthResolution(
                    ctx=AccessContext(
                        subject=legacy_subject,
                        roles=roles,
                        workspace_id=legacy_workspace_id,
                    ),
                    auth_mode=auth_mode,
                    identity_source="legacy_acl",
                    deprecated_legacy_acl=True,
                )

        if auth_mode in {"strict", "strict_oauth"} and request is not None:
            raise PermissionError("missing_bearer_token")

        return AuthResolution(
            ctx=AccessContext(subject="anonymous", roles=tuple(), workspace_id="default"),
            auth_mode=auth_mode,
            identity_source="anonymous",
            deprecated_legacy_acl=False,
        )

    @staticmethod
    def _extract_header_token(request: Any | None) -> str | None:
        if request is None:
            return None
        headers = getattr(request, "headers", None)
        if headers is None:
            return None
        auth_value = headers.get("authorization")
        if not isinstance(auth_value, str):
            return None
        prefix = "bearer "
        if auth_value.lower().startswith(prefix):
            token = auth_value[len(prefix):].strip()
            return token or None
        return None
