from __future__ import annotations

from _pytest.monkeypatch import MonkeyPatch

from kb_mcp.config import AppConfig


def test_app_config_parses_oauth_env(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("KB_AUTH_MODE", "strict_oauth")
    monkeypatch.setenv("KB_OAUTH_ISSUER_URL", "https://issuer.example")
    monkeypatch.setenv("KB_OAUTH_AUDIENCE", "hybrid-kb-mcp")
    monkeypatch.setenv("KB_OAUTH_JWKS_URL", "https://issuer.example/.well-known/jwks.json")
    monkeypatch.setenv("KB_OAUTH_REQUIRED_SCOPES", "mcp.read,mcp.write")

    cfg = AppConfig.from_env()

    assert cfg.auth_mode == "strict_oauth"
    assert cfg.oauth_issuer_url == "https://issuer.example"
    assert cfg.oauth_audience == "hybrid-kb-mcp"
    assert cfg.oauth_jwks_url == "https://issuer.example/.well-known/jwks.json"
    assert cfg.oauth_required_scopes == ("mcp.read", "mcp.write")
