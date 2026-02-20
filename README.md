# hybrid-kb-mcp

Hybrid Retrieval MCP server for knowledge base retrieval and persistent conversation memory.

## What This Project Provides

- MCP tools: `kb.search`, `kb.graph_expand`, `kb.explain`
- Memory tools: `kb.memory.upsert`, `kb.memory.search`, `kb.memory.delete`
- Ingestion tools: `kb.ingest.filesystem`, `kb.ingest.git_diff`
- ACL-protected resources: `kb://doc/*`, `kb://chunk/*`, `kb://entity/*`, `kb://memory/*`
- Hybrid retrieval (vector + graph + rerank) with fallback behavior
- Metadata persistence (`sqlite` default, `postgres` optional)

## Documentation Map

- Full install/deploy/config guide: `docs/install_deploy_config.md`
- Operational incident handling: `docs/runbook.md`
- LLM tool routing policy: `docs/tool_selection_policy.md`
- KPI template: `docs/kpi_report_template.md`
- Current KPI report: `docs/kpi_report.md`

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev,rerank]
cp .env.example .env
```

Run stdio transport:

```bash
python -m kb_mcp.server.transport_stdio
```

Run Streamable HTTP transport:

```bash
set -a; source .env; set +a
python -m kb_mcp.server.transport_http
```

Run Docker Desktop stack:

```bash
mkdir -p .docker-data/qdrant .docker-data/neo4j/data .docker-data/mcp
docker compose up -d --build
```

## MCP Endpoint

- HTTP MCP: `http://127.0.0.1:8080/mcp`
- Stdio entrypoint: `python -m kb_mcp.server.transport_stdio`

## Security Notes

- Use `KB_AUTH_MODE=strict` for new deployments.
- In `dual` mode precedence is:
  - `Authorization` header -> `payload.jwt_bearer` -> legacy payload ACL.
- HTTP transport supports Host/Origin restrictions via `KB_TRANSPORT_ALLOWED_HOSTS` and `KB_TRANSPORT_ALLOWED_ORIGINS`.

## Benchmark Commands

```bash
python3 bench/run_benchmark.py --top-k 10 --enforce-gates --output bench/report_no_rerank.json
python3 bench/run_benchmark.py --top-k 10 --rerank --enforce-gates --output bench/report_with_rerank.json
```
