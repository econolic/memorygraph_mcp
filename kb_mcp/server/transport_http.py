from __future__ import annotations

from kb_mcp.bootstrap import build_deps
from kb_mcp.config import AppConfig
from kb_mcp.ingest.auto_ingest import AutoIngestService
from kb_mcp.logging import configure_logging
from kb_mcp.server.app import create_mcp_server


def run_http() -> None:
    cfg = AppConfig.from_env()
    configure_logging()
    deps = build_deps(cfg)
    auto_ingest = AutoIngestService(deps)
    auto_ingest.start()
    server = create_mcp_server(deps)
    try:
        server.run(transport="streamable-http")
    finally:
        auto_ingest.stop()


if __name__ == "__main__":
    run_http()
