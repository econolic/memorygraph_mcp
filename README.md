# hybrid-kb-mcp

Hybrid Retrieval MCP server for knowledge base retrieval and persistent conversation memory.

## What This Project Provides

- MCP tools: `kb.search`, `kb.graph_expand`, `kb.explain`
- Memory tools: `kb.memory.upsert`, `kb.memory.search`, `kb.memory.delete`
- Ingestion tools: `kb.ingest.filesystem`, `kb.ingest.git_diff`
- ACL-protected resources: `kb://doc/*`, `kb://chunk/*`, `kb://entity/*`, `kb://memory/*`
- Hybrid retrieval (vector + graph + rerank) with fallback behavior
- Metadata persistence (`sqlite` default, `postgres` optional, `memory` for tests/dev)
- Runtime feature flags for retrieval quality:
  - `KB_FUSION_MODE=linear|rrf`
  - `KB_CHUNKING_MODE=char|sentence`
  - `KB_GRAPH_ENFORCE_OBJECT_ACL=true|false`
- Embeddings and entity extraction quality controls:
  - `KB_EMBEDDING_BATCH_SIZE`
  - `KB_EMBEDDING_MODEL_REVISION`
  - `KB_EMBEDDING_CACHE_ENABLED`
  - `KB_EMBEDDING_CACHE_MAX_ITEMS`
  - `KB_ENTITY_EXTRACTION_*`
- Default auto-ingest loop (enabled by default):
  - `KB_AUTO_INGEST_ENABLED=true`
  - `KB_AUTO_INGEST_ROOTS=/app/.kb_mcp/project_sync,./kb_mcp`
  - `KB_AUTO_INGEST_WORKSPACE_ID=w1`
  - `KB_AUTO_INGEST_ACL_SUBJECT=u1`
  - `KB_AUTO_INGEST_INTERVAL_S=900`
  - `KB_AUTO_INGEST_RUN_ON_START=true`

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
- Graph retrieval enforces object ACL by default (`KB_GRAPH_ENFORCE_OBJECT_ACL=true`).

## Runtime Defaults

- Auto-actualization is enabled by default and starts at server boot.
- Default roots: `/app/.kb_mcp/project_sync` and `./kb_mcp`.
- Default target identity: `workspace_id=w1`, `acl_subject=u1`.
- On startup, look for log lines:
  - `auto_ingest_started`
  - `auto_ingest_cycle`
- For retrieval diagnostics, inspect `kb.search` response fields:
  - `debug.filters_effective`
  - `debug.graph_acl_enforced`
  - `debug.fusion_mode`
  - `debug.graph_seed_count`
  - `debug.graph_node_count`
  - `debug.graph_chunk_bonus_count`
  - `debug.graph_nonzero`
- Optional observability exporters:
  - `KB_OTEL_ENABLED=true` + `KB_OTEL_EXPORTER_OTLP_*`
  - `KB_PROMETHEUS_ENABLED=true` + `KB_PROMETHEUS_PORT=9464`

## Benchmark Commands

```bash
python3 bench/run_benchmark.py --top-k 10 --enforce-gates \
  --metadata-dsn sqlite:///./.kb_mcp/bench_metadata_no_rerank.db \
  --output bench/report_no_rerank.json
python3 bench/run_benchmark.py --top-k 10 --rerank --enforce-gates \
  --metadata-dsn sqlite:///./.kb_mcp/bench_metadata_with_rerank.db \
  --output bench/report_with_rerank.json
```
