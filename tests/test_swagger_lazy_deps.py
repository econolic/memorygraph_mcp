from __future__ import annotations

from kb_mcp.server import swagger_app


def test_swagger_dependencies_are_initialized_lazily_once(monkeypatch) -> None:
    sentinel = object()
    calls = 0

    def fake_build_deps() -> object:
        nonlocal calls
        calls += 1
        return sentinel

    monkeypatch.setattr(swagger_app, "deps", None)
    monkeypatch.setattr(swagger_app, "build_deps", fake_build_deps)

    assert swagger_app.get_deps() is sentinel
    assert swagger_app.get_deps() is sentinel
    assert calls == 1
