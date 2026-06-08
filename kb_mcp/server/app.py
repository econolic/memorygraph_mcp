from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.auth.settings import AuthSettings
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import AnyHttpUrl

from kb_mcp.bootstrap import AppDeps, build_deps
from kb_mcp.server.helpers import resource_server_url
from kb_mcp.server.tools import (
    register_search_tools,
    register_memory_tools,
    register_ingest_tools,
    register_system_tools,
)
from kb_mcp.server.resources import register_resources
from kb_mcp.server.prompts import register_prompts

if TYPE_CHECKING:
    FastContext = Context[Any, Any, Any]
else:
    FastContext = Context

REGISTERED_TOOLS = [
    "kb_health",
    "kb_route",
    "kb_search",
    "kb_graph_expand",
    "kb_explain",
    "kb_memory_upsert",
    "kb_memory_search",
    "kb_memory_delete",
    "kb_ingest_filesystem",
    "kb_ingest_git_diff",
]

REGISTERED_RESOURCES = [
    "kb://doc/{doc_id}",
    "kb://chunk/{chunk_id}",
    "kb://entity/{entity_id}",
    "kb://memory/{memory_id}",
    "kb://policy/tool-selection",
]

REGISTERED_PROMPTS = [
    "kb.answer_with_citations",
    "kb.tool_selection_policy",
    "kb.incident_triage",
    "kb.memory_grounded_reply",
]


def create_mcp_server(deps: AppDeps | None = None) -> FastMCP:
    deps = deps or build_deps()
    cfg = deps.config

    transport_security = None
    if cfg.transport_security_enabled:
        allowed_hosts = list(cfg.transport_allowed_hosts) or [
            "127.0.0.1:*",
            "localhost:*",
            "[::1]:*",
        ]
        allowed_origins = list(cfg.transport_allowed_origins) or [
            "http://127.0.0.1:*",
            "http://localhost:*",
            "http://[::1]:*",
        ]
        transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=allowed_hosts,
            allowed_origins=allowed_origins,
        )

    token_verifier = None
    auth_settings = None
    if cfg.auth_mode == "strict_oauth":
        token_verifier = deps.auth.oauth_token_verifier()
        if token_verifier is None:
            raise ValueError(
                "strict_oauth requires KB_OAUTH_ISSUER_URL and KB_OAUTH_JWKS_URL to be configured"
            )
        auth_settings = AuthSettings(
            issuer_url=cast(AnyHttpUrl, cfg.oauth_issuer_url),
            resource_server_url=cast(
                AnyHttpUrl,
                resource_server_url(host=cfg.http_host, port=cfg.http_port),
            ),
            required_scopes=list(cfg.oauth_required_scopes) or None,
        )

    mcp = FastMCP(
        cfg.service_name,
        token_verifier=token_verifier,
        stateless_http=True,
        json_response=True,
        host=cfg.http_host,
        port=cfg.http_port,
        streamable_http_path="/mcp",
        auth=auth_settings,
        transport_security=transport_security,
    )

    # Register tools, resources, prompts
    register_system_tools(
        mcp=mcp,
        deps=deps,
        registered_tools=REGISTERED_TOOLS,
        registered_resources=REGISTERED_RESOURCES,
        registered_prompts=REGISTERED_PROMPTS,
    )
    register_search_tools(mcp=mcp, deps=deps)
    register_memory_tools(mcp=mcp, deps=deps)
    register_ingest_tools(mcp=mcp, deps=deps)
    register_resources(mcp=mcp, deps=deps)
    register_prompts(mcp=mcp)

    return mcp
