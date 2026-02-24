from __future__ import annotations

import pytest

from kb_mcp.config import AppConfig, security_validation_summary, validate_security_config


def _cfg(**overrides: object) -> AppConfig:
    base = AppConfig(
        vector_backend="memory",
        graph_backend="memory",
        metadata_backend="memory",
    )
    return AppConfig(**{**base.__dict__, **overrides})


def test_strict_mode_rejects_placeholder_jwt_secret() -> None:
    cfg = _cfg(auth_mode="strict", jwt_secret="change-me")
    with pytest.raises(ValueError, match="KB_AUTH_MODE=strict"):
        validate_security_config(cfg, transport="http")


def test_dual_mode_network_bind_rejects_placeholder_jwt_secret() -> None:
    cfg = _cfg(auth_mode="dual", http_host="0.0.0.0", jwt_secret="change-me")
    with pytest.raises(ValueError, match="non-localhost HTTP bind"):
        validate_security_config(cfg, transport="http")


def test_dual_mode_localhost_allows_placeholder_with_warning() -> None:
    cfg = _cfg(auth_mode="dual", http_host="127.0.0.1", jwt_secret="change-me")
    warnings = validate_security_config(cfg, transport="http")
    assert warnings
    assert "localhost development" in warnings[0]


def test_strict_oauth_requires_issuer_and_jwks() -> None:
    cfg = _cfg(auth_mode="strict_oauth")
    with pytest.raises(ValueError, match="KB_OAUTH_ISSUER_URL"):
        validate_security_config(cfg, transport="http")


def test_security_summary_marks_localhost_bind() -> None:
    cfg = _cfg(auth_mode="dual", http_host="127.0.0.1", jwt_secret="change-me")
    summary = security_validation_summary(cfg, transport="stdio")
    assert summary["bind_scope"] == "localhost"
    assert summary["transport"] == "stdio"
    assert summary["jwt_secret_weak"] is True

