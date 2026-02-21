from __future__ import annotations

import asyncio

import pytest

from kb_mcp.security.oidc import OidcJwksTokenVerifier


class _SigningKey:
    key = "public-key"


class _JwkClient:
    def get_signing_key_from_jwt(self, token: str) -> _SigningKey:
        assert token
        return _SigningKey()


def test_decode_token_enforces_required_scopes(monkeypatch: pytest.MonkeyPatch) -> None:
    verifier = OidcJwksTokenVerifier(
        issuer_url="https://issuer.example",
        audience="aud",
        jwks_url="https://issuer.example/jwks",
        required_scopes=("mcp.read",),
    )
    monkeypatch.setattr(verifier, "_jwk_client", _JwkClient())
    monkeypatch.setattr("kb_mcp.security.oidc.jwt.get_unverified_header", lambda _token: {"alg": "RS256"})
    monkeypatch.setattr(
        "kb_mcp.security.oidc.jwt.decode",
        lambda *args, **kwargs: {"sub": "u1", "workspace_id": "w1", "scope": "mcp.write"},
    )

    with pytest.raises(PermissionError):
        verifier.decode_token("token")


def test_verify_token_returns_access_token(monkeypatch: pytest.MonkeyPatch) -> None:
    verifier = OidcJwksTokenVerifier(
        issuer_url="https://issuer.example",
        audience="aud",
        jwks_url="https://issuer.example/jwks",
        required_scopes=("mcp.read",),
    )
    monkeypatch.setattr(verifier, "_jwk_client", _JwkClient())
    monkeypatch.setattr("kb_mcp.security.oidc.jwt.get_unverified_header", lambda _token: {"alg": "RS256"})
    monkeypatch.setattr(
        "kb_mcp.security.oidc.jwt.decode",
        lambda *args, **kwargs: {
            "sub": "u1",
            "workspace_id": "w1",
            "scope": "mcp.read mcp.write",
            "exp": 123456,
            "azp": "client-1",
        },
    )

    token = asyncio.run(verifier.verify_token("token"))
    assert token is not None
    assert token.client_id == "client-1"
    assert token.scopes == ["mcp.read", "mcp.write"]
    assert token.expires_at == 123456
