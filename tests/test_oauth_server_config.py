from __future__ import annotations

import pytest

from kb_mcp.bootstrap import build_deps
from kb_mcp.config import AppConfig
from kb_mcp.server.app import create_mcp_server


def _base_cfg() -> AppConfig:
    return AppConfig(
        vector_backend="memory",
        graph_backend="memory",
        metadata_backend="memory",
    )


def test_strict_oauth_requires_oidc_config() -> None:
    cfg = _base_cfg()
    cfg = AppConfig(**{**cfg.__dict__, "auth_mode": "strict_oauth"})
    deps = build_deps(cfg)
    with pytest.raises(ValueError):
        create_mcp_server(deps)


def test_strict_oauth_builds_server_with_auth_settings() -> None:
    cfg = _base_cfg()
    cfg = AppConfig(
        **{
            **cfg.__dict__,
            "auth_mode": "strict_oauth",
            "oauth_issuer_url": "https://issuer.example",
            "oauth_audience": "hybrid-kb-mcp",
            "oauth_jwks_url": "https://issuer.example/.well-known/jwks.json",
            "oauth_required_scopes": ("mcp.read", "mcp.write"),
        }
    )
    deps = build_deps(cfg)
    server = create_mcp_server(deps)
    assert server.settings.auth is not None
    assert list(server.settings.auth.required_scopes or []) == ["mcp.read", "mcp.write"]
