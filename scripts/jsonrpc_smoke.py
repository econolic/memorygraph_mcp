#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from typing import Any
from urllib import request


def rpc(url: str, *, method: str, params: dict[str, Any], token: str, request_id: str) -> dict[str, Any]:
    body = json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}).encode()
    req = request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    with request.urlopen(req, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Unexpected JSON-RPC response: {payload!r}")
    return payload


def tool_call(url: str, *, name: str, arguments: dict[str, Any], token: str) -> dict[str, Any]:
    response = rpc(
        url,
        method="tools/call",
        params={"name": name, "arguments": arguments},
        token=token,
        request_id=name,
    )
    result = response.get("result")
    if not isinstance(result, dict) or result.get("isError") is True:
        raise RuntimeError(f"Tool call failed for {name}: {response}")
    structured = result.get("structuredContent")
    if not isinstance(structured, dict):
        raise RuntimeError(f"Tool call returned no structuredContent for {name}: {response}")
    return structured


def main() -> int:
    parser = argparse.ArgumentParser(description="Run minimal JSON-RPC smoke checks against Hybrid KB MCP.")
    parser.add_argument("--url", default="http://127.0.0.1:8080/mcp")
    parser.add_argument("--token", required=True)
    parser.add_argument("--workspace-id", default="w1")
    parser.add_argument("--subject", default="u1")
    parser.add_argument("--query", default="Hybrid Retrieval MCP server")
    parser.add_argument("--foreign-token", default="")
    args = parser.parse_args()

    tools_response = rpc(args.url, method="tools/list", params={}, token=args.token, request_id="tools")
    tools = {tool["name"] for tool in tools_response.get("result", {}).get("tools", [])}
    required = {"kb.health", "kb.route", "kb.search", "kb.ingest.filesystem"}
    missing = sorted(required - tools)
    if missing:
        raise RuntimeError(f"Missing tools: {missing}")

    health = tool_call(args.url, name="kb.health", arguments={}, token=args.token)
    route = tool_call(
        args.url,
        name="kb.route",
        arguments={"payload": {"query": args.query, "requested_mode": "hybrid", "include_memory": True}},
        token=args.token,
    )
    search = tool_call(
        args.url,
        name="kb.search",
        arguments={
            "payload": {
                "query": args.query,
                "mode": "hybrid",
                "top_k": 5,
                "workspace_id": args.workspace_id,
                "session_id": "jsonrpc-smoke",
                "include_memory": False,
                "filters": {
                    "acl": {
                        "subject": args.subject,
                        "workspace_id": args.workspace_id,
                        "roles": [],
                    }
                },
                "graph": {"expand_depth": 1, "edge_types": [], "max_nodes": 50},
                "rerank": {"enabled": False, "provider": "cross_encoder", "top_n": 5},
            }
        },
        token=args.token,
    )

    deny_checked = False
    results = search.get("results", [])
    if args.foreign_token and results:
        first = results[0]
        if isinstance(first, dict) and isinstance(first.get("uri"), str):
            deny = rpc(
                args.url,
                method="resources/read",
                params={"uri": first["uri"]},
                token=args.foreign_token,
                request_id="resource-deny",
            )
            deny_text = json.dumps(deny)
            if "forbidden" not in deny_text:
                raise RuntimeError(f"Expected forbidden resource read with foreign token: {deny}")
            deny_checked = True

    print(
        json.dumps(
            {
                "ok": True,
                "tools": sorted(tools),
                "health_ok": health.get("ok") is True,
                "route_intent": route.get("intent"),
                "search_result_count": len(results) if isinstance(results, list) else 0,
                "resource_acl_deny_checked": deny_checked,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
