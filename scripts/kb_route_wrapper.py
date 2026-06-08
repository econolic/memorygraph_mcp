#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx

SERVER_REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class WrapperConfig:
    transport: str
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
    stdio_command: str
    stdio_args: tuple[str, ...]
    stdio_cwd: str
    stdio_env_file: str
    stdio_disable_auto_ingest: bool


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name, default)
    return value.strip() if isinstance(value, str) else default


def _parse_json_text(text: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _extract_tool_output(*, structured: Any, content: Any, fallback: Any = None) -> dict[str, Any]:
    if isinstance(structured, dict):
        return structured

    if isinstance(content, list):
        for item in content:
            # HTTP JSON dict path
            if isinstance(item, dict):
                if item.get("type") == "text" and isinstance(item.get("text"), str):
                    parsed = _parse_json_text(item["text"])
                    if parsed is not None:
                        return parsed
                continue

            # MCP SDK pydantic models path (e.g., TextContent)
            text = getattr(item, "text", None)
            if isinstance(text, str):
                parsed = _parse_json_text(text)
                if parsed is not None:
                    return parsed

    if isinstance(fallback, dict):
        return fallback

    raise RuntimeError("Unexpected MCP tool response format")


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
        if isinstance(result, dict) and result.get("isError") is True:
            content = result.get("content", [])
            error_text = ""
            if isinstance(content, list) and content:
                first = content[0]
                if isinstance(first, dict):
                    text = first.get("text")
                    if isinstance(text, str):
                        error_text = text
            raise RuntimeError(f"MCP tool error {name}: {error_text or result}")
        return _extract_tool_output(
            structured=result.get("structuredContent"),
            content=result.get("content", []),
            fallback=result,
        )


def _acl_subject(cfg: WrapperConfig) -> dict[str, Any]:
    return {
        "subject": cfg.subject,
        "roles": [],
        "workspace_id": cfg.workspace_id,
        "jwt_bearer": cfg.bearer_token or None,
    }


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
                "acl": _acl_subject(cfg),
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


def _legacy_route_fallback(cfg: WrapperConfig, reason: str) -> dict[str, Any]:
    plan: list[dict[str, Any]] = []
    if cfg.include_memory:
        plan.append(
            {
                "tool": "kb_memory_search",
                "purpose": "Compatibility fallback: load memory before search because kb_route is unavailable.",
                "when": "always",
                "required": False,
            }
        )
    plan.append(
        {
            "tool": "kb_search",
            "purpose": "Compatibility fallback: execute direct search because kb_route is unavailable.",
            "when": "always",
            "required": True,
        }
    )
    return {
        "policy_version": "legacy-compat",
        "intent": "memory_context" if cfg.include_memory else "fact_lookup",
        "mode": cfg.requested_mode,
        "route_reason": reason,
        "recommended_tools": [step["tool"] for step in plan],
        "execution_plan": plan,
        "constraints": {
            "compatibility_mode": True,
            "router_tool": "kb_route",
        },
    }


def execute_pipeline(client: McpHttpClient, cfg: WrapperConfig, query: str) -> dict[str, Any]:
    try:
        route = client.call_tool(
            "kb_route",
            {
                "payload": {
                    "query": query,
                    "requested_mode": cfg.requested_mode,
                    "include_memory": cfg.include_memory,
                }
            },
        )
    except RuntimeError as exc:
        msg = str(exc)
        if "Unknown tool: kb_route" in msg:
            route = _legacy_route_fallback(cfg, "kb_route_unavailable_http_fallback")
        else:
            raise

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

        if tool == "kb_memory_search":
            outputs["memory_search"] = client.call_tool(tool, _memory_search_payload(cfg, query))
            continue

        if tool == "kb_search":
            search_out = client.call_tool(tool, _search_payload(cfg, query, route))
            outputs["search"] = search_out
            continue

        if tool == "kb_graph_expand":
            if search_out is None:
                skipped.append({"tool": tool, "reason": "missing_kb_search_output"})
                continue
            seed_entities = _collect_seed_entities(search_out, cfg.max_seed_entities)
            if not seed_entities:
                skipped.append({"tool": tool, "reason": "no_seed_entities_in_search_results"})
                continue
            outputs["graph_expand"] = client.call_tool(tool, _graph_expand_payload(cfg, seed_entities))
            outputs["graph_expand_seeds"] = seed_entities
            continue

        if tool == "kb_explain":
            if search_out is None:
                skipped.append({"tool": tool, "reason": "missing_kb_search_output"})
                continue
            uris = _collect_result_uris(search_out, cfg.explain_top_uris)
            if not uris:
                skipped.append({"tool": tool, "reason": "no_result_uris_in_search_results"})
                continue
            outputs["explain"] = client.call_tool(tool, _explain_payload(cfg, uris))
            outputs["explain_uris"] = uris
            continue

        if tool == "kb_memory_delete":
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


def _load_env_file(path: str) -> dict[str, str]:
    if not path:
        return {}
    file_path = Path(path)
    if not file_path.exists():
        return {}
    try:
        from dotenv import dotenv_values  # type: ignore[import-not-found]

        raw = dotenv_values(file_path)
        return {str(k): str(v) for k, v in raw.items() if k and v is not None}
    except Exception:
        out: dict[str, str] = {}
        for line in file_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            out[key.strip()] = value.strip().strip('"').strip("'")
        return out


async def _execute_pipeline_stdio_async(cfg: WrapperConfig, query: str) -> dict[str, Any]:
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    child_env = dict(os.environ)
    child_env.update(_load_env_file(cfg.stdio_env_file))
    if cfg.stdio_disable_auto_ingest:
        child_env["KB_AUTO_INGEST_ENABLED"] = "false"

    server = StdioServerParameters(
        command=cfg.stdio_command,
        args=list(cfg.stdio_args),
        env=child_env,
        cwd=cfg.stdio_cwd or str(SERVER_REPO_ROOT),
    )

    async def call_tool(session: ClientSession, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        result = await session.call_tool(
            name=name,
            arguments=arguments,
            read_timeout_seconds=timedelta(seconds=cfg.timeout_s),
        )
        if getattr(result, "isError", False):
            raise RuntimeError(f"MCP tool error {name}: {result}")
        return _extract_tool_output(
            structured=getattr(result, "structuredContent", None),
            content=getattr(result, "content", []),
            fallback=None,
        )

    async with stdio_client(server) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = await session.list_tools()
            tool_names = {tool.name for tool in tools.tools}
            if "kb_route" not in tool_names:
                route = _legacy_route_fallback(cfg, "kb_route_unavailable_stdio_fallback")
            else:
                route = await call_tool(
                    session,
                    "kb_route",
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

                if tool == "kb_memory_search":
                    outputs["memory_search"] = await call_tool(
                        session, tool, _memory_search_payload(cfg, query)
                    )
                    continue

                if tool == "kb_search":
                    search_out = await call_tool(session, tool, _search_payload(cfg, query, route))
                    outputs["search"] = search_out
                    continue

                if tool == "kb_graph_expand":
                    if search_out is None:
                        skipped.append({"tool": tool, "reason": "missing_kb_search_output"})
                        continue
                    seed_entities = _collect_seed_entities(search_out, cfg.max_seed_entities)
                    if not seed_entities:
                        skipped.append({"tool": tool, "reason": "no_seed_entities_in_search_results"})
                        continue
                    outputs["graph_expand"] = await call_tool(
                        session, tool, _graph_expand_payload(cfg, seed_entities)
                    )
                    outputs["graph_expand_seeds"] = seed_entities
                    continue

                if tool == "kb_explain":
                    if search_out is None:
                        skipped.append({"tool": tool, "reason": "missing_kb_search_output"})
                        continue
                    uris = _collect_result_uris(search_out, cfg.explain_top_uris)
                    if not uris:
                        skipped.append({"tool": tool, "reason": "no_result_uris_in_search_results"})
                        continue
                    outputs["explain"] = await call_tool(session, tool, _explain_payload(cfg, uris))
                    outputs["explain_uris"] = uris
                    continue

                if tool == "kb_memory_delete":
                    if not cfg.allow_memory_delete:
                        skipped.append(
                            {
                                "tool": tool,
                                "reason": "memory_delete_blocked",
                                "hint": "pass --allow-memory-delete to execute",
                            }
                        )
                        continue
                    outputs["memory_delete"] = await call_tool(session, tool, _memory_delete_payload(cfg))
                    continue

                skipped.append({"tool": tool, "reason": "unsupported_tool_in_execution_plan"})

            if skipped:
                outputs["skipped_steps"] = skipped
            return outputs


def execute_pipeline_stdio(cfg: WrapperConfig, query: str) -> dict[str, Any]:
    import anyio

    return anyio.run(_execute_pipeline_stdio_async, cfg, query)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Wrapper that calls kb_route first, then executes the MCP execution_plan."
    )
    parser.add_argument("query", help="User query to route and execute against MCP.")
    parser.add_argument("--transport", choices=["http", "stdio"], default="http")
    parser.add_argument(
        "--endpoint",
        default=_env("KB_WRAPPER_MCP_ENDPOINT", "http://127.0.0.1:8080/mcp"),
        help="HTTP MCP endpoint (for --transport http).",
    )
    parser.add_argument(
        "--token",
        default=_env("KB_WRAPPER_BEARER_TOKEN"),
        help="Bearer token value without 'Bearer ' prefix (required for --transport http).",
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
    parser.add_argument("--no-memory", action="store_true", help="Disable memory in routing/search.")
    parser.add_argument(
        "--allow-memory-delete",
        action="store_true",
        help="Allow executing kb_memory_delete if kb_route recommends it.",
    )

    parser.add_argument(
        "--stdio-command",
        default=str(SERVER_REPO_ROOT / ".venv" / "bin" / "python"),
        help="Executable used to launch stdio MCP server (for --transport stdio).",
    )
    parser.add_argument(
        "--stdio-module",
        default="kb_mcp.server.transport_stdio",
        help="Python module to run for stdio server (for --transport stdio).",
    )
    parser.add_argument(
        "--stdio-cwd",
        default=str(SERVER_REPO_ROOT),
        help="Working directory for the stdio server process.",
    )
    parser.add_argument(
        "--stdio-env-file",
        default=str(SERVER_REPO_ROOT / ".env"),
        help="dotenv file to load into stdio server process environment.",
    )
    parser.add_argument(
        "--stdio-disable-auto-ingest",
        action="store_true",
        help="Force KB_AUTO_INGEST_ENABLED=false for the stdio child process.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])

    if args.transport == "http" and not args.token:
        print("Missing bearer token for HTTP transport. Pass --token or set KB_WRAPPER_BEARER_TOKEN.", file=sys.stderr)
        return 2

    cfg = WrapperConfig(
        transport=args.transport,
        endpoint=args.endpoint,
        bearer_token=args.token or "",
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
        stdio_command=args.stdio_command,
        stdio_args=("-m", args.stdio_module),
        stdio_cwd=args.stdio_cwd,
        stdio_env_file=args.stdio_env_file,
        stdio_disable_auto_ingest=args.stdio_disable_auto_ingest,
    )

    try:
        if cfg.transport == "stdio":
            result = execute_pipeline_stdio(cfg, args.query)
        else:
            client = McpHttpClient(cfg.endpoint, cfg.bearer_token, cfg.timeout_s)
            result = execute_pipeline(client, cfg, args.query)
    except Exception as exc:  # pragma: no cover - CLI error path
        print(f"Wrapper failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
