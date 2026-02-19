from __future__ import annotations

from kb_mcp.bootstrap import build_deps
from kb_mcp.config import AppConfig
from kb_mcp.logging import configure_logging
from kb_mcp.server.app import create_mcp_server


def run_stdio() -> None:
    cfg = AppConfig.from_env()
    configure_logging()
    deps = build_deps(cfg)
    server = create_mcp_server(deps)
    server.run(transport="stdio")


if __name__ == "__main__":
    run_stdio()
