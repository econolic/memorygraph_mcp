from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jwt
import pytest
from starlette.testclient import TestClient

from kb_mcp.bootstrap import build_deps
from kb_mcp.config import AppConfig
from kb_mcp.server.app import create_mcp_server

pytestmark = pytest.mark.external


def _token(secret: str, sub: str, workspace_id: str) -> str:
    return str(jwt.encode({"sub": sub, "workspace_id": workspace_id, "roles": ["reader"]}, secret, algorithm="HS256"))


def _client(cfg: AppConfig | None = None) -> TestClient:
    cfg = cfg or AppConfig(
        auth_mode="strict",
        jwt_secret="secret",
        vector_backend="memory",
        graph_backend="memory",
        metadata_backend="memory",
        transport_security_enabled=True,
        transport_allowed_hosts=("127.0.0.1", "127.0.0.1:*", "testserver", "testserver:*"),
        transport_allowed_origins=("http://127.0.0.1", "http://127.0.0.1:*", "http://testserver"),
    )
    deps = build_deps(cfg)
    server = create_mcp_server(deps)
    app = server.streamable_http_app()
    return TestClient(app, base_url="http://127.0.0.1")


def _rpc(
    *,
    client: TestClient,
    method: str,
    params: dict[str, Any],
    bearer: str | None,
) -> dict[str, Any]:
    headers = {"Accept": "application/json, text/event-stream"}
    if bearer is not None:
        headers["Authorization"] = f"Bearer {bearer}"
    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": "test", "method": method, "params": params},
        headers=headers,
    )
    response.raise_for_status()
    payload = response.json()
    assert isinstance(payload, dict)
    return payload


def _tool_call(
    *,
    client: TestClient,
    name: str,
    arguments: dict[str, Any],
    bearer: str | None,
) -> dict[str, Any]:
    return _rpc(
        client=client,
        method="tools/call",
        params={"name": name, "arguments": arguments},
        bearer=bearer,
    )


def _tool_structured_content(resp: dict[str, Any]) -> dict[str, Any]:
    result = resp.get("result", {})
    assert isinstance(result, dict)
    assert result.get("isError") is False
    structured = result.get("structuredContent")
    assert isinstance(structured, dict)
    return structured


def _tool_error_text(resp: dict[str, Any]) -> str:
    result = resp.get("result", {})
    assert isinstance(result, dict)
    assert result.get("isError") is True
    content = result.get("content", [])
    assert isinstance(content, list) and content
    first = content[0]
    assert isinstance(first, dict)
    text = first.get("text")
    assert isinstance(text, str)
    return text


def _search_payload(*, workspace_id: str, subject: str, query: str) -> dict[str, Any]:
    return {
        "payload": {
            "query": query,
            "mode": "hybrid",
            "top_k": 5,
            "workspace_id": workspace_id,
            "session_id": "s1",
            "include_memory": False,
            "filters": {"acl": {"subject": subject, "workspace_id": workspace_id, "roles": []}},
            "graph": {"expand_depth": 1, "edge_types": [], "max_nodes": 50},
            "rerank": {"enabled": False, "provider": "cross_encoder", "top_n": 5},
        }
    }


def test_http_strict_rejects_missing_bearer() -> None:
    with _client() as client:
        resp = _tool_call(
            client=client,
            name="kb.search",
            arguments=_search_payload(workspace_id="w1", subject="u1", query="alpha"),
            bearer=None,
        )
        error_text = _tool_error_text(resp)
        assert "missing_bearer_token" in error_text


def test_http_bearer_identity_precedence_over_payload_spoof() -> None:
    with _client() as client:
        token = _token("secret", "header_user", "w_header")
        resp = _tool_call(
            client=client,
            name="kb.search",
            arguments=_search_payload(workspace_id="w_spoof", subject="spoof_user", query="alpha"),
            bearer=token,
        )
        structured = _tool_structured_content(resp)
        decision_trace = structured.get("decision_trace", {})
        debug = structured.get("debug", {})
        assert isinstance(decision_trace, dict)
        assert isinstance(debug, dict)
        assert decision_trace.get("identity_source") == "authorization_header"
        assert decision_trace.get("auth_mode") == "strict"
        assert debug.get("payload_workspace_ignored") is True
        assert isinstance(debug.get("filters_effective"), dict)
        assert debug.get("graph_acl_enforced") is True
        assert decision_trace.get("fusion_mode") == "linear"
        assert debug.get("fusion_mode") == "linear"
        assert isinstance(debug.get("graph_seed_count"), int)
        assert isinstance(debug.get("graph_node_count"), int)
        assert isinstance(debug.get("graph_chunk_bonus_count"), int)
        assert isinstance(debug.get("graph_nonzero"), bool)
        assert structured.get("ok") is True
        assert structured.get("error_code") is None
        assert isinstance(structured.get("meta"), dict)


def test_http_tools_list_and_health_contract() -> None:
    with _client() as client:
        token = _token("secret", "u1", "w1")
        tools_resp = _rpc(client=client, method="tools/list", params={}, bearer=token)
        tools = {tool["name"] for tool in tools_resp["result"]["tools"]}
        assert "kb.health" in tools

        health_resp = _tool_call(client=client, name="kb.health", arguments={}, bearer=token)
        health = _tool_structured_content(health_resp)
        assert health.get("ok") is True
        assert health.get("service_name") == "hybrid-kb-mcp"
        assert "kb.search" in health.get("tools", [])
        assert "kb://policy/tool-selection" in health.get("resources", [])
        assert "kb.tool_selection_policy" in health.get("prompts", [])


def test_http_resource_acl_denies_foreign_workspace_access(tmp_path: Path) -> None:
    doc = tmp_path / "secure_doc.md"
    doc.write_text("Only workspace w1 should read this content.", encoding="utf-8")

    with _client() as client:
        token_w1 = _token("secret", "u1", "w1")
        token_w2 = _token("secret", "u2", "w2")

        ingest_resp = _tool_call(
            client=client,
            name="kb.ingest.filesystem",
            arguments={"root_path": str(tmp_path), "workspace_id": "w1", "acl_subject": "u1"},
            bearer=token_w1,
        )
        ingest_structured = _tool_structured_content(ingest_resp)
        assert ingest_structured.get("created") == 1

        search_resp = _tool_call(
            client=client,
            name="kb.search",
            arguments=_search_payload(workspace_id="w1", subject="u1", query="workspace w1 read"),
            bearer=token_w1,
        )
        search_structured = _tool_structured_content(search_resp)
        results = search_structured.get("results", [])
        assert isinstance(results, list) and results
        first = results[0]
        assert isinstance(first, dict)
        chunk_uri = first.get("uri")
        assert isinstance(chunk_uri, str) and chunk_uri.startswith("kb://chunk/")

        foreign_read = _rpc(
            client=client,
            method="resources/read",
            params={"uri": chunk_uri},
            bearer=token_w2,
        )
        foreign_result = foreign_read.get("result", {})
        assert isinstance(foreign_result, dict)
        foreign_contents = foreign_result.get("contents", [])
        assert isinstance(foreign_contents, list) and foreign_contents
        foreign_first = foreign_contents[0]
        assert isinstance(foreign_first, dict)
        foreign_payload = json.loads(str(foreign_first.get("text", "{}")))
        assert foreign_payload.get("error") == "forbidden"
        assert foreign_payload.get("ok") is False
        assert foreign_payload.get("error_code") == "PERMISSION_DENIED"

        owner_read = _rpc(
            client=client,
            method="resources/read",
            params={"uri": chunk_uri},
            bearer=token_w1,
        )
        owner_result = owner_read.get("result", {})
        assert isinstance(owner_result, dict)
        owner_contents = owner_result.get("contents", [])
        assert isinstance(owner_contents, list) and owner_contents
        owner_first = owner_contents[0]
        assert isinstance(owner_first, dict)
        owner_payload = json.loads(str(owner_first.get("text", "{}")))
        assert owner_payload.get("error") is None
        assert owner_payload.get("ok") is True
        assert owner_payload.get("uri") == chunk_uri


def test_ingest_outside_allowlist_returns_controlled_error(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    denied = tmp_path / "denied"
    allowed.mkdir()
    denied.mkdir()
    (denied / "secret.md").write_text("should not be scanned", encoding="utf-8")

    cfg = AppConfig(
        auth_mode="strict",
        jwt_secret="secret",
        vector_backend="memory",
        graph_backend="memory",
        metadata_backend="memory",
        ingest_allowed_roots=(str(allowed.resolve()),),
        transport_security_enabled=True,
        transport_allowed_hosts=("127.0.0.1", "127.0.0.1:*", "testserver", "testserver:*"),
        transport_allowed_origins=("http://127.0.0.1", "http://127.0.0.1:*", "http://testserver"),
    )

    with _client(cfg) as client:
        token = _token("secret", "u1", "w1")
        resp = _tool_call(
            client=client,
            name="kb.ingest.filesystem",
            arguments={"root_path": str(denied), "workspace_id": "w1", "acl_subject": "u1"},
            bearer=token,
        )
        structured = _tool_structured_content(resp)
        assert structured.get("ok") is False
        assert structured.get("error_code") == "PERMISSION_DENIED"
        assert structured.get("created") == 0
        assert structured.get("updated") == 0


def test_ingest_dry_run_does_not_write_documents(tmp_path: Path) -> None:
    (tmp_path / "dry.md").write_text("dry run candidate content", encoding="utf-8")
    cfg = AppConfig(
        auth_mode="strict",
        jwt_secret="secret",
        vector_backend="memory",
        graph_backend="memory",
        metadata_backend="memory",
        ingest_allowed_roots=(str(tmp_path.resolve()),),
        transport_security_enabled=True,
        transport_allowed_hosts=("127.0.0.1", "127.0.0.1:*", "testserver", "testserver:*"),
        transport_allowed_origins=("http://127.0.0.1", "http://127.0.0.1:*", "http://testserver"),
    )

    with _client(cfg) as client:
        token = _token("secret", "u1", "w1")
        dry_resp = _tool_call(
            client=client,
            name="kb.ingest.filesystem",
            arguments={
                "root_path": str(tmp_path),
                "workspace_id": "w1",
                "acl_subject": "u1",
                "dry_run": True,
            },
            bearer=token,
        )
        dry_structured = _tool_structured_content(dry_resp)
        assert dry_structured.get("ok") is True
        assert dry_structured.get("dry_run") is True
        assert dry_structured.get("created") == 1

        search_resp = _tool_call(
            client=client,
            name="kb.search",
            arguments=_search_payload(workspace_id="w1", subject="u1", query="candidate content"),
            bearer=token,
        )
        assert _tool_structured_content(search_resp).get("results") == []

        ingest_resp = _tool_call(
            client=client,
            name="kb.ingest.filesystem",
            arguments={"root_path": str(tmp_path), "workspace_id": "w1", "acl_subject": "u1"},
            bearer=token,
        )
        ingest_structured = _tool_structured_content(ingest_resp)
        assert ingest_structured.get("dry_run") is False
        assert ingest_structured.get("created") == 1
