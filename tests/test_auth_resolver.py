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
