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
  - important: ingest is checksum-driven; unchanged files are skipped (no forced graph backfill)

## Tool Descriptions (User View)

- `kb.search`: find relevant knowledge snippets with citations.
- `kb.graph_expand`: show entity relations, dependency chains, and impact paths.
- `kb.explain`: explain why retrieved results are relevant.
- `kb.memory.upsert`: save confirmed facts/decisions/preferences for a user/workspace.
- `kb.memory.search`: retrieve previously saved user/workspace context.
- `kb.memory.delete`: delete saved memory by IDs or all memory for a subject.
- `kb.ingest.filesystem`: ingest knowledge from a folder (full scan with incremental updates).
- `kb.ingest.git_diff`: ingest only files changed in git diff (faster incremental refresh).

## Documentation Map

- Full install/deploy/config guide: `docs/install_deploy_config.md`
- Operational incident handling: `docs/runbook.md`
- LLM tool routing policy: `docs/tool_selection_policy.md`
- LLM↔MCP context control roadmap: `docs/llm_mcp_context_control_plan.md`
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

- Use `KB_AUTH_MODE=strict` for JWT deployments, or `KB_AUTH_MODE=strict_oauth` for OIDC/JWKS deployments.
- In `dual` mode precedence is:
  - `Authorization` header -> `payload.jwt_bearer` -> legacy payload ACL.
- In `strict_oauth` mode, HTTP requests require `Authorization: Bearer ...`; token is validated against OIDC JWKS.
- HTTP transport supports Host/Origin restrictions via `KB_TRANSPORT_ALLOWED_HOSTS` and `KB_TRANSPORT_ALLOWED_ORIGINS`.
- Graph retrieval enforces object ACL by default (`KB_GRAPH_ENFORCE_OBJECT_ACL=true`).

## Session and Identity Model

- Identity is resolved from bearer token claims (`sub`, `workspace_id`) in strict modes.
- `workspace_id` is the main boundary for knowledge isolation.
- Knowledge base content (documents/chunks/entities) is shared inside the same workspace, subject to ACL.
- Memory records are stored with `workspace_id`, `subject`, and `session_id`.
- Current retrieval behavior for memory is subject/workspace-scoped; `session_id` is accepted in contracts but not used as a hard filter in memory search.

Practical implications when switching agents/sessions:

- Same `sub` + same `workspace_id` + different agent session:
  - the agent can still access prior memory for that user/workspace.
- Different `workspace_id`:
  - data is isolated; cross-workspace access is denied.
- Different `sub` in same workspace:
  - visibility depends on ACL (`acl_allow`) of stored objects.

## Runtime Defaults

- Auto-actualization is enabled by default and starts at server boot.
- Auto-actualization is incremental by checksum. Startup/interval cycles do not force reindex for unchanged files.
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
- Optional strict OAuth settings:
  - `KB_OAUTH_ISSUER_URL`, `KB_OAUTH_AUDIENCE`, `KB_OAUTH_JWKS_URL`, `KB_OAUTH_REQUIRED_SCOPES`
- Auto-ingest hardening controls:
  - `KB_AUTO_INGEST_FULL_INTERVAL_CYCLES`
  - `KB_AUTO_INGEST_GIT_SINCE_REF`
  - `KB_AUTO_INGEST_RETRY_ATTEMPTS`
  - `KB_AUTO_INGEST_RETRY_BACKOFF_S`

## Data Portability and Backup

You can move the knowledge base to another machine.

Docker runtime (local persistent mode):

1. Stop services:
   - `docker compose down`
2. Copy data directories and config:
   - `.docker-data/qdrant`
   - `.docker-data/neo4j/data`
   - `.docker-data/mcp`
   - `.env`
3. On target machine, place files in the same paths and run:
   - `docker compose up -d --build`

Notes:

- Keep source and target on compatible image versions (Qdrant/Neo4j/MCP).
- For consistent snapshots, copy data while services are stopped.
- MCP currently has no dedicated export/import tool; portability is done at storage level (filesystem/DB backup).

External DB mode:

- Qdrant and Neo4j: use native backup/restore of the managed services.
- Metadata Postgres: use `pg_dump` / `pg_restore`.

## Benchmark Commands

```bash
python3 bench/run_benchmark.py --top-k 10 --enforce-gates \
  --metadata-dsn sqlite:///./.kb_mcp/bench_metadata_no_rerank.db \
  --output bench/report_no_rerank.json
python3 bench/run_benchmark.py --top-k 10 --rerank --enforce-gates \
  --metadata-dsn sqlite:///./.kb_mcp/bench_metadata_with_rerank.db \
  --output bench/report_with_rerank.json
```

## strict_oauth Smoke

Run reproducible smoke (local test issuer + JWKS + signed token + `tools/list`):

```bash
./scripts/smoke_strict_oauth.sh
```

Manual guide and request example: `docs/install_deploy_config.md` (section: strict_oauth smoke with local test JWKS/issuer).
