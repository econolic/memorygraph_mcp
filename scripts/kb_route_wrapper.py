#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class WrapperConfig:
    endpoint: str
    bearer_token: str
    workspace_id: str
    subject: str
    session_id: str
    requested_mode: str
    include_memory: bool
    top_k: int
    graph_expand_depth: int
    graph_max_nodes: int
    explain_top_uris: int
    max_seed_entities: int
    allow_memory_delete: bool
    timeout_s: float


class McpHttpClient:
    def __init__(self, endpoint: str, bearer_token: str, timeout_s: float) -> None:
        self._endpoint = endpoint
        self._headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {bearer_token}",
        }
        self._timeout_s = timeout_s

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        req_id = str(uuid.uuid4())
        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
        with httpx.Client(timeout=self._timeout_s) as client:
            resp = client.post(self._endpoint, headers=self._headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        if "error" in data:
            raise RuntimeError(f"MCP tool error {name}: {data['error']}")
        result = data.get("result", {})
        structured = result.get("structuredContent")
        if isinstance(structured, dict):
            return structured
        # Fallback for servers/versions that return direct JSON content in content[]
        content = result.get("content", [])
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text", "")
                    if isinstance(text, str):
                        try:
                            parsed = json.loads(text)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(parsed, dict):
                            return parsed
        if isinstance(result, dict):
            return result
        raise RuntimeError(f"Unexpected MCP response for {name}")


def _memory_search_payload(cfg: WrapperConfig, query: str) -> dict[str, Any]:
    return {
        "payload": {
            "query": query,
            "workspace_id": cfg.workspace_id,
            "subject": cfg.subject,
            "session_id": cfg.session_id,
            "top_k": min(10, cfg.top_k),
        }
    }


def _search_payload(cfg: WrapperConfig, query: str, route: dict[str, Any]) -> dict[str, Any]:
    route_mode = route.get("mode", cfg.requested_mode)
    if route_mode not in {"vector", "graph", "hybrid"}:
        route_mode = cfg.requested_mode
    return {
        "payload": {
            "query": query,
            "mode": route_mode,
            "top_k": cfg.top_k,
            "workspace_id": cfg.workspace_id,
            "session_id": cfg.session_id,
            "include_memory": cfg.include_memory,
            "filters": {
                "tags": [],
                "sources": [],
                "updated_after": None,
                "acl": {
                    "subject": cfg.subject,
                    "roles": [],
                    "workspace_id": cfg.workspace_id,
                },
            },
            "graph": {
                "expand_depth": cfg.graph_expand_depth,
                "edge_types": [],
                "max_nodes": cfg.graph_max_nodes,
            },
            "rerank": {
                "enabled": False,
                "provider": "cross_encoder",
                "top_n": min(10, cfg.top_k),
            },
        }
    }


def _collect_seed_entities(search_result: dict[str, Any], limit: int) -> list[str]:
    seeds: list[str] = []
    seen: set[str] = set()
    for item in search_result.get("results", []):
        if not isinstance(item, dict):
            continue
        entities = item.get("entities", [])
        if not isinstance(entities, list):
            continue
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            uri = entity.get("uri")
            if not isinstance(uri, str) or not uri or uri in seen:
                continue
            seen.add(uri)
            seeds.append(uri)
            if len(seeds) >= limit:
                return seeds
    return seeds


def _collect_result_uris(search_result: dict[str, Any], limit: int) -> list[str]:
    uris: list[str] = []
    seen: set[str] = set()
    for item in search_result.get("results", []):
        if not isinstance(item, dict):
            continue
        uri = item.get("uri")
        if not isinstance(uri, str) or not uri or uri in seen:
            continue
        seen.add(uri)
        uris.append(uri)
        if len(uris) >= limit:
            break
    return uris


def _graph_expand_payload(cfg: WrapperConfig, seed_entities: list[str]) -> dict[str, Any]:
    return {
        "payload": {
            "seed_entities": seed_entities,
            "depth": cfg.graph_expand_depth,
            "edge_types": [],
            "max_nodes": cfg.graph_max_nodes,
            "workspace_id": cfg.workspace_id,
            "subject": cfg.subject,
        }
    }


def _explain_payload(cfg: WrapperConfig, uris: list[str]) -> dict[str, Any]:
    return {
        "payload": {
            "uris": uris,
            "workspace_id": cfg.workspace_id,
            "subject": cfg.subject,
        }
    }


def _memory_delete_payload(cfg: WrapperConfig) -> dict[str, Any]:
    return {
        "payload": {
            "workspace_id": cfg.workspace_id,
            "subject": cfg.subject,
            "all_for_subject": True,
            "ids": [],
        }
    }


def execute_pipeline(client: McpHttpClient, cfg: WrapperConfig, query: str) -> dict[str, Any]:
    route = client.call_tool(
        "kb.route",
        {
            "payload": {
                "query": query,
                "requested_mode": cfg.requested_mode,
                "include_memory": cfg.include_memory,
            }
        },
    )

    outputs: dict[str, Any] = {"route": route}
    skipped: list[dict[str, Any]] = []
    search_out: dict[str, Any] | None = None

    execution_plan = route.get("execution_plan", [])
    if not isinstance(execution_plan, list):
        execution_plan = []

    for step in execution_plan:
        if not isinstance(step, dict):
            continue
        tool = step.get("tool")
        if not isinstance(tool, str):
            continue

        if tool == "kb.memory.search":
            outputs["memory_search"] = client.call_tool(tool, _memory_search_payload(cfg, query))
            continue

        if tool == "kb.search":
            search_out = client.call_tool(tool, _search_payload(cfg, query, route))
            outputs["search"] = search_out
            continue

        if tool == "kb.graph_expand":
            if search_out is None:
                skipped.append({"tool": tool, "reason": "missing_kb.search_output"})
                continue
            seed_entities = _collect_seed_entities(search_out, cfg.max_seed_entities)
            if not seed_entities:
                skipped.append({"tool": tool, "reason": "no_seed_entities_in_search_results"})
                continue
            outputs["graph_expand"] = client.call_tool(tool, _graph_expand_payload(cfg, seed_entities))
            outputs["graph_expand_seeds"] = seed_entities
            continue

        if tool == "kb.explain":
            if search_out is None:
                skipped.append({"tool": tool, "reason": "missing_kb.search_output"})
                continue
            uris = _collect_result_uris(search_out, cfg.explain_top_uris)
            if not uris:
                skipped.append({"tool": tool, "reason": "no_result_uris_in_search_results"})
                continue
            outputs["explain"] = client.call_tool(tool, _explain_payload(cfg, uris))
            outputs["explain_uris"] = uris
            continue

        if tool == "kb.memory.delete":
            if not cfg.allow_memory_delete:
                skipped.append(
                    {
                        "tool": tool,
                        "reason": "memory_delete_blocked",
                        "hint": "pass --allow-memory-delete to execute",
                    }
                )
                continue
            outputs["memory_delete"] = client.call_tool(tool, _memory_delete_payload(cfg))
            continue

        skipped.append({"tool": tool, "reason": "unsupported_tool_in_execution_plan"})

    if skipped:
        outputs["skipped_steps"] = skipped
    return outputs


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name, default)
    return value.strip() if isinstance(value, str) else default


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Client wrapper for hybrid-kb-mcp that always executes kb.route first."
    )
    parser.add_argument("query", help="User query to route and execute against MCP.")
    parser.add_argument(
        "--endpoint",
        default=_env("KB_WRAPPER_MCP_ENDPOINT", "http://127.0.0.1:8080/mcp"),
        help="HTTP MCP endpoint (default: %(default)s or KB_WRAPPER_MCP_ENDPOINT).",
    )
    parser.add_argument(
        "--token",
        default=_env("KB_WRAPPER_BEARER_TOKEN"),
        help="Bearer token value without 'Bearer ' prefix (or KB_WRAPPER_BEARER_TOKEN).",
    )
    parser.add_argument("--workspace-id", default=_env("KB_WRAPPER_WORKSPACE_ID", "w1"))
    parser.add_argument("--subject", default=_env("KB_WRAPPER_SUBJECT", "u1"))
    parser.add_argument("--session-id", default=_env("KB_WRAPPER_SESSION_ID", "s1"))
    parser.add_argument("--requested-mode", default="hybrid", choices=["vector", "graph", "hybrid"])
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--graph-expand-depth", type=int, default=2)
    parser.add_argument("--graph-max-nodes", type=int, default=100)
    parser.add_argument("--explain-top-uris", type=int, default=5)
    parser.add_argument("--max-seed-entities", type=int, default=20)
    parser.add_argument("--timeout-s", type=float, default=20.0)
    parser.add_argument(
        "--no-memory",
        action="store_true",
        help="Disable memory in kb.route and kb.search payloads.",
    )
    parser.add_argument(
        "--allow-memory-delete",
        action="store_true",
        help="Allow executing kb.memory.delete if kb.route recommends it.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if not args.token:
        print(
            "Missing bearer token. Pass --token or set KB_WRAPPER_BEARER_TOKEN.",
            file=sys.stderr,
        )
        return 2

    cfg = WrapperConfig(
        endpoint=args.endpoint,
        bearer_token=args.token,
        workspace_id=args.workspace_id,
        subject=args.subject,
        session_id=args.session_id,
        requested_mode=args.requested_mode,
        include_memory=not args.no_memory,
        top_k=max(1, args.top_k),
        graph_expand_depth=max(0, args.graph_expand_depth),
        graph_max_nodes=max(1, args.graph_max_nodes),
        explain_top_uris=max(1, args.explain_top_uris),
        max_seed_entities=max(1, args.max_seed_entities),
        allow_memory_delete=args.allow_memory_delete,
        timeout_s=max(1.0, args.timeout_s),
    )

    client = McpHttpClient(cfg.endpoint, cfg.bearer_token, cfg.timeout_s)
    try:
        result = execute_pipeline(client, cfg, args.query)
    except Exception as exc:  # pragma: no cover - CLI error path
        print(f"Wrapper failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
