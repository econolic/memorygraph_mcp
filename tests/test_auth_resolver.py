from __future__ import annotations

import jwt
import pytest

from kb_mcp.config import AppConfig
from kb_mcp.security.auth import JwtAuthService


class _Request:
    def __init__(self, authorization: str | None = None) -> None:
        self.headers: dict[str, str] = {}
        if authorization is not None:
            self.headers["authorization"] = authorization


def _token(secret: str, sub: str, workspace_id: str) -> str:
    return str(jwt.encode({"sub": sub, "workspace_id": workspace_id, "roles": ["reader"]}, secret, algorithm="HS256"))


class _FakeOidcVerifier:
    def __init__(self, *, claims: dict[str, object], enabled: bool = True) -> None:
        self._claims = claims
        self.enabled = enabled
        self.tokens: list[str] = []

    def decode_token(self, token: str) -> dict[str, object]:
        self.tokens.append(token)
        if token == "bad":
            raise ValueError("invalid_token")
        return dict(self._claims)


def test_dual_mode_prefers_authorization_header_over_legacy_payload() -> None:
    cfg = AppConfig(auth_mode="dual", jwt_secret="secret")
    auth = JwtAuthService(cfg)
    token = _token("secret", "header_user", "w_header")
    req = _Request(authorization=f"Bearer {token}")

    result = auth.resolve_identity(
        request=req,
        payload_acl={"subject": "legacy_user", "workspace_id": "w_legacy", "roles": []},
    )
    assert result.identity_source == "authorization_header"
    assert result.ctx.subject == "header_user"
    assert result.ctx.workspace_id == "w_header"


def test_strict_mode_rejects_http_request_without_bearer() -> None:
    cfg = AppConfig(auth_mode="strict", jwt_secret="secret")
    auth = JwtAuthService(cfg)
    req = _Request()
    with pytest.raises(PermissionError):
        auth.resolve_identity(
            request=req,
            payload_acl={"subject": "legacy_user", "workspace_id": "w_legacy", "roles": []},
        )


def test_strict_mode_rejects_payload_jwt_without_header() -> None:
    cfg = AppConfig(auth_mode="strict", jwt_secret="secret")
    auth = JwtAuthService(cfg)
    payload_token = _token("secret", "payload_user", "w_payload")
    req = _Request()
    with pytest.raises(PermissionError):
        auth.resolve_identity(
            request=req,
            payload_acl={"jwt_bearer": payload_token, "subject": "legacy_user", "workspace_id": "w_legacy"},
        )


def test_strict_oauth_accepts_header_identity() -> None:
    cfg = AppConfig(auth_mode="strict_oauth")
    verifier = _FakeOidcVerifier(
        claims={"sub": "oauth_user", "workspace_id": "w_oauth", "roles": ["reader"]},
    )
    auth = JwtAuthService(cfg, oidc_verifier=verifier)
    req = _Request(authorization="Bearer oauth_token")
    result = auth.resolve_identity(request=req, payload_acl={"subject": "legacy", "workspace_id": "w_legacy"})
    assert result.identity_source == "authorization_header"
    assert result.ctx.subject == "oauth_user"
    assert result.ctx.workspace_id == "w_oauth"


def test_strict_oauth_rejects_payload_jwt_for_http() -> None:
    cfg = AppConfig(auth_mode="strict_oauth")
    verifier = _FakeOidcVerifier(claims={"sub": "oauth_user", "workspace_id": "w_oauth"})
    auth = JwtAuthService(cfg, oidc_verifier=verifier)
    req = _Request()
    with pytest.raises(PermissionError):
        auth.resolve_identity(
            request=req,
            payload_acl={"jwt_bearer": "oauth_payload", "subject": "legacy", "workspace_id": "w_legacy"},
        )


def test_strict_oauth_allows_payload_jwt_for_stdio() -> None:
    cfg = AppConfig(auth_mode="strict_oauth")
    verifier = _FakeOidcVerifier(claims={"sub": "oauth_user", "workspace_id": "w_oauth"})
    auth = JwtAuthService(cfg, oidc_verifier=verifier)
    result = auth.resolve_identity(
        request=None,
        payload_acl={"jwt_bearer": "oauth_payload", "subject": "legacy", "workspace_id": "w_legacy"},
    )
    assert result.identity_source == "payload_jwt"
    assert result.ctx.subject == "oauth_user"
