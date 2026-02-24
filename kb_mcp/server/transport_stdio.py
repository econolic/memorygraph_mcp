from __future__ import annotations

import logging

from kb_mcp.bootstrap import build_deps
from kb_mcp.config import AppConfig, security_validation_summary, validate_security_config
from kb_mcp.ingest.auto_ingest import AutoIngestService
from kb_mcp.logging import configure_logging
from kb_mcp.observability.metrics import start_prometheus_exporter
from kb_mcp.server.app import create_mcp_server


def run_stdio() -> None:
    cfg = AppConfig.from_env()
    configure_logging()
    logger = logging.getLogger(__name__)
    warnings = validate_security_config(cfg, transport="stdio")
    logger.info("security_config_validated", extra={"extra": security_validation_summary(cfg, transport="stdio")})
    for warning in warnings:
        logger.warning("security_config_warning", extra={"extra": {"warning": warning}})
    deps = build_deps(cfg)
    if cfg.prometheus_enabled and deps.metrics.prometheus_registry is not None:
        start_prometheus_exporter(port=cfg.prometheus_port, registry=deps.metrics.prometheus_registry)
    auto_ingest = AutoIngestService(deps)
    auto_ingest.start()
    server = create_mcp_server(deps)
    try:
        server.run(transport="stdio")
    finally:
        auto_ingest.stop()


if __name__ == "__main__":
    run_stdio()
