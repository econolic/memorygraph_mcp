# Hybrid KB MCP: Installation, Deployment, and Configuration Guide

This guide is the canonical operator manual for running `hybrid-kb-mcp` locally with persistent data and secure MCP access.

## 1. Purpose and Audience

Use this document if you need to:

- install and run the MCP server from source;
- deploy the full local stack (MCP + Qdrant + Neo4j) in Docker Desktop;
- connect MCP to external/managed data stores;
- enforce strict HTTP authentication and ACL behavior;
- validate runtime, persistence, and KPI gates before release.

Primary audience: developers, operators, and QA engineers running local/runtime verification.

## 2. Runtime Architecture

Core components:

- MCP server (`kb_mcp`) exposing tools/resources via stdio and Streamable HTTP.
- Vector backend: Qdrant (`kb_chunks`, `kb_memory` collections).
- Graph backend: Neo4j (entities, chunks, document relations).
- Metadata backend: SQLite (default), Postgres (optional), or in-memory mode for tests/dev.

Primary data flows:

1. Ingestion (`kb.ingest.filesystem` / `kb.ingest.git_diff`) writes metadata, vectors, and graph edges.
2. Retrieval (`kb.search`) runs hybrid retrieval (vector + graph + rerank).
3. Conversation memory (`kb.memory.*`) persists and retrieves subject/workspace-scoped memory.
4. Resources (`kb://doc/*`, `kb://chunk/*`, `kb://entity/*`, `kb://memory/*`) are ACL-checked server-side.
5. Auto-ingest loop (enabled by default) refreshes configured roots on startup and by interval.

## 3. Prerequisites

| Requirement | Minimum | Notes |
|---|---|---|
| OS | Linux/macOS/Windows (WSL2 recommended on Windows) | Docker Desktop supported |
| Python | 3.11+ | Required for source install |
| Docker | Docker Desktop recent stable | Required for full compose stack |
| Git | 2.30+ | Needed for repo + git-diff ingestion |
| RAM | 8 GB | 12+ GB recommended with rerank models |
| Open ports | 8080, 6333, 7474, 7687 | MCP, Qdrant, Neo4j HTTP/Bolt |

## 4. Deployment Modes

- Path A (source/local): fastest for development and debugging.
- Path B (Docker Desktop): recommended for stable local runtime with persistence.
- Path C (external DB mode): keep MCP local/containerized, connect to managed Qdrant/Neo4j/Postgres.

## 5. Configuration Model (`.env`)

Start from:

```bash
cp .env.example .env
```

Key variables:

- Transport/auth:
  - `KB_HTTP_HOST`, `KB_HTTP_PORT`
  - `KB_AUTH_MODE=dual|strict|strict_oauth`
  - `KB_JWT_SECRET`, `KB_JWT_ALGORITHM`
  - `KB_OAUTH_ISSUER_URL`, `KB_OAUTH_AUDIENCE`, `KB_OAUTH_JWKS_URL`, `KB_OAUTH_REQUIRED_SCOPES`
  - `KB_TRANSPORT_SECURITY_ENABLED`
  - `KB_TRANSPORT_ALLOWED_HOSTS`
  - `KB_TRANSPORT_ALLOWED_ORIGINS`
- Backends:
  - `KB_VECTOR_BACKEND=qdrant|memory`
  - `KB_GRAPH_BACKEND=neo4j|memory`
  - `KB_METADATA_BACKEND=sqlite|postgres|memory`
  - `KB_METADATA_DSN`
- Qdrant:
  - `KB_QDRANT_URL`, `KB_QDRANT_COLLECTION_CHUNKS`, `KB_QDRANT_COLLECTION_MEMORY`
- Neo4j:
  - `KB_NEO4J_URI`, `KB_NEO4J_USER`, `KB_NEO4J_PASSWORD`, `KB_NEO4J_DATABASE`
- Embeddings:
  - `KB_EMBEDDING_PROVIDER=local|openai_compatible`
  - `KB_EMBEDDING_MODEL`, `KB_EMBEDDING_MODEL_REVISION`
  - `KB_EMBEDDING_BASE_URL`, `KB_EMBEDDING_API_KEY`, `KB_EMBEDDING_DIMENSIONS`
  - `KB_EMBEDDING_BATCH_SIZE`
  - `KB_EMBEDDING_CACHE_ENABLED`, `KB_EMBEDDING_CACHE_MAX_ITEMS`
- Entity extraction:
  - `KB_ENTITY_EXTRACTION_MIN_SYMBOL_LEN`, `KB_ENTITY_EXTRACTION_MIN_TERM_LEN`
  - `KB_ENTITY_SYMBOL_ALLOW_PATTERN`, `KB_ENTITY_TABLE_ALLOW_PATTERN`, `KB_ENTITY_TERM_ALLOW_PATTERN`
  - `KB_ENTITY_EXTRACTION_STOPWORDS`
- Retrieval quality/runtime flags:
  - `KB_FUSION_MODE=linear|rrf`
  - `KB_CHUNKING_MODE=char|sentence`
  - `KB_GRAPH_ENFORCE_OBJECT_ACL=true|false`
  - `KB_AUTO_INGEST_ENABLED=true|false`
  - `KB_AUTO_INGEST_ROOTS=<comma-separated directories>`
  - `KB_AUTO_INGEST_WORKSPACE_ID=<workspace>`
  - `KB_AUTO_INGEST_ACL_SUBJECT=<subject>`
  - `KB_AUTO_INGEST_INTERVAL_S=<seconds>`
  - `KB_AUTO_INGEST_RUN_ON_START=true|false`
  - `KB_AUTO_INGEST_FULL_INTERVAL_CYCLES=<N>`
  - `KB_AUTO_INGEST_GIT_SINCE_REF=<git ref>`
  - `KB_AUTO_INGEST_RETRY_ATTEMPTS=<N>`
  - `KB_AUTO_INGEST_RETRY_BACKOFF_S=<seconds>`
- Observability:
  - `KB_OTEL_ENABLED=true|false`
  - `KB_OTEL_EXPORTER_OTLP_ENDPOINT`
  - `KB_OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf|grpc`
  - `KB_PROMETHEUS_ENABLED=true|false`
  - `KB_PROMETHEUS_PORT=9464`

Default auto-ingest profile:

- `KB_AUTO_INGEST_ENABLED=true`
- `KB_AUTO_INGEST_ROOTS=/app/.kb_mcp/project_sync,./kb_mcp`
- `KB_AUTO_INGEST_WORKSPACE_ID=w1`
- `KB_AUTO_INGEST_ACL_SUBJECT=u1`
- `KB_AUTO_INGEST_INTERVAL_S=900`
- `KB_AUTO_INGEST_RUN_ON_START=true`
- `KB_AUTO_INGEST_FULL_INTERVAL_CYCLES=8`
- `KB_AUTO_INGEST_GIT_SINCE_REF=HEAD~1`
- `KB_AUTO_INGEST_RETRY_ATTEMPTS=3`
- `KB_AUTO_INGEST_RETRY_BACKOFF_S=1.5`

Security recommendation for HTTP runtime:

- use `KB_AUTH_MODE=strict` (JWT) or `KB_AUTH_MODE=strict_oauth` (OIDC/JWKS);
- for `strict`: set strong `KB_JWT_SECRET`;
- for `strict_oauth`: set `KB_OAUTH_ISSUER_URL`, `KB_OAUTH_JWKS_URL`, `KB_OAUTH_AUDIENCE`;
- keep Host/Origin allowlists constrained to trusted local endpoints.
- keep `KB_GRAPH_ENFORCE_OBJECT_ACL=true` for production.

## 6. Install Path A: Source (venv, no Docker)

### 6.1 Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev,rerank]
cp .env.example .env
```

For local host safety (non-container), set in `.env`:

```bash
KB_HTTP_HOST=127.0.0.1
KB_HTTP_PORT=8080
KB_AUTH_MODE=strict
KB_VECTOR_BACKEND=memory
KB_GRAPH_BACKEND=memory
KB_METADATA_BACKEND=sqlite
KB_METADATA_DSN=sqlite:///./.kb_mcp/metadata.db
```

Load env and run HTTP transport:

```bash
set -a; source .env; set +a
python -m kb_mcp.server.transport_http
```

Run stdio transport (alternative):

```bash
python -m kb_mcp.server.transport_stdio
```

### 6.2 Create JWT token for strict mode

Generate a strong secret first (example):

```bash
python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
```

Set the generated value in `.env` as `KB_JWT_SECRET`, then create a token:

```bash
python3 - <<'PY'
import jwt
import os
secret = os.environ["KB_JWT_SECRET"]
print(jwt.encode({"sub": "u1", "workspace_id": "w1", "roles": ["reader"]}, secret, algorithm="HS256"))
PY
```

### 6.3 Smoke checks (HTTP MCP)

`tools/list` with bearer:

```bash
TOKEN="<paste_token>"
curl -sS http://127.0.0.1:8080/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{"jsonrpc":"2.0","id":"1","method":"tools/list","params":{}}'
```

Strict mode negative check (without bearer):

```bash
curl -sS http://127.0.0.1:8080/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":"2","method":"tools/call","params":{"name":"kb.search","arguments":{"payload":{"query":"test","mode":"hybrid","top_k":3,"workspace_id":"w1","session_id":"s1","include_memory":false,"filters":{"acl":{"subject":"u1","workspace_id":"w1","roles":[]}},"graph":{"expand_depth":1,"edge_types":[],"max_nodes":50},"rerank":{"enabled":false,"provider":"cross_encoder","top_n":3}}}}}'
```

Expected in strict mode: error containing `missing_bearer_token`.

## 7. Install Path B: Docker Desktop (persistent)

### 7.1 Prepare directories and env

```bash
cp .env.example .env
mkdir -p .docker-data/qdrant .docker-data/neo4j/data .docker-data/mcp
```

Recommended in `.env`:

```bash
KB_AUTH_MODE=strict
KB_HTTP_HOST=0.0.0.0
KB_HTTP_PORT=8080
KB_METADATA_BACKEND=sqlite
KB_METADATA_DSN=sqlite:///./.kb_mcp/metadata.db
```

### 7.2 Start stack

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f mcp
```

If `KB_PROMETHEUS_ENABLED=true`, metrics are exposed by the app on `KB_PROMETHEUS_PORT`.

- With current `docker-compose.yml`, host mapping is fixed to `9464:9464`, so default endpoint is:
  - `http://127.0.0.1:9464/metrics`
- If you change `KB_PROMETHEUS_PORT`, update compose port mapping accordingly.

### 7.3 Verify persistence after restart

1. Ingest test data via `kb.ingest.filesystem`.
2. Confirm searchable chunk via `kb.search`.
3. Restart services:

```bash
docker compose restart
```

4. Repeat `kb.search`; results should still be available.

### 7.4 Verify auto-ingest startup cycle

After `docker compose up -d --build`:

```bash
docker compose logs --since 2m mcp | rg "auto_ingest_started|auto_ingest_cycle"
```

Expected:

- `auto_ingest_started` with configured roots/workspace/subject.
- At least one `auto_ingest_cycle` line with counters (`created`, `updated`, `failed_roots`).

Persistent host paths (default):

- Qdrant: `./.docker-data/qdrant`
- Neo4j: `./.docker-data/neo4j/data`
- MCP metadata/checksums SQLite: `./.docker-data/mcp`

## 8. Install Path C: External/Managed DB mode

Set external endpoints in `.env`:

```bash
KB_QDRANT_URL=http://<qdrant-host>:6333
KB_NEO4J_URI=bolt://<neo4j-host>:7687
KB_NEO4J_USER=<neo4j-user>
KB_NEO4J_PASSWORD=<neo4j-password>
KB_NEO4J_DATABASE=neo4j
KB_METADATA_BACKEND=postgres
KB_METADATA_DSN=postgresql+psycopg://<user>:<password>@<postgres-host>:5432/<db>
```

Then run:

```bash
docker compose up -d --build
```

Note for this repository compose setup:

- `docker-compose.yml` still defines local `qdrant` and `neo4j` services as dependencies of `mcp`.
- In external mode, MCP uses endpoints from `KB_QDRANT_URL`/`KB_NEO4J_URI`, while local services may remain unused.
- For strict MCP-only runtime without local DB containers, prefer Path A (source runtime) or a custom compose override.

Network notes:

- containerized MCP must resolve hosts from container network (`host.docker.internal` or routable DNS/IP);
- local source runtime may use `127.0.0.1`/LAN endpoints directly;
- if endpoints are TLS-enabled, provide matching `https://` / secure connection settings.

If metadata bootstrap fails due to Postgres privileges:

```sql
GRANT USAGE, CREATE ON SCHEMA public TO <user>;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO <user>;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO <user>;
```

## 9. Auth and Security Hardening

### 9.1 Auth modes

- `dual`:
  - precedence: `Authorization` header -> `payload.jwt_bearer` -> legacy payload ACL (`subject/workspace_id`);
  - intended only for migration compatibility.
- `strict`:
  - HTTP requests without valid bearer are rejected;
  - recommended default for all new deployments.
- `strict_oauth`:
  - HTTP requests require `Authorization: Bearer ...`;
  - bearer tokens are validated via OIDC issuer + JWKS and optional required scopes;
  - use for enterprise SSO / IdP-managed access tokens.

### 9.2 JWT / OIDC token claims requirements

Required claims:

- `sub` (subject)
- `workspace_id`

Optional:

- `roles` (list)

OIDC scope check:

- if `KB_OAUTH_REQUIRED_SCOPES` is set, all listed scopes must be present in token `scope`/`scp`.

### 9.3 Transport protections

Use:

- `KB_TRANSPORT_SECURITY_ENABLED=true`
- narrow `KB_TRANSPORT_ALLOWED_HOSTS`
- narrow `KB_TRANSPORT_ALLOWED_ORIGINS`

Default host in app config is `127.0.0.1`; Docker overrides to `0.0.0.0` via `.env`/compose.

## 10. MCP Client Integration

### 10.1 Codex MCP registration

Add to `/root/.codex/config.toml`:

```toml
[mcp_servers.hybrid_kb_mcp]
url = "http://127.0.0.1:8080/mcp"
startup_timeout_sec = 60
```

Restart Codex session after updating config.

### 10.2 Generic HTTP MCP client behavior

Use JSON-RPC over POST to `/mcp` with:

- `Content-Type: application/json`
- `Accept: application/json, text/event-stream`
- `Authorization: Bearer <token>` in strict/strict_oauth modes

Minimal `tools/call` example (`kb.memory.search`):

```bash
curl -sS http://127.0.0.1:8080/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{"jsonrpc":"2.0","id":"mem1","method":"tools/call","params":{"name":"kb.memory.search","arguments":{"payload":{"query":"previous decision","workspace_id":"w1","subject":"u1","session_id":"s1","top_k":5}}}}'
```

## 11. Data Lifecycle and Retention

- Ingestion:
  - `kb.ingest.filesystem`: full scan + incremental checksum updates.
  - `kb.ingest.git_diff`: ingest only changed files by git diff baseline.
  - auto-ingest loop: periodic background refresh from `KB_AUTO_INGEST_ROOTS`.
- Memory:
  - saved per `workspace_id` + `subject`, optional `session_id` context;
  - retention is indefinite by default;
  - delete via `kb.memory.delete` (`ids` or `all_for_subject=true`).
- ACL:
  - deny-by-default policy;
  - resources/tools enforce workspace/subject constraints server-side.

## 12. Verification Checklist

### 12.1 Functional

1. `tools/list` returns expected KB tools.
2. `kb.ingest.filesystem` ingests at least one document.
3. `kb.search` returns results with citations.
4. `kb.memory.upsert` -> `kb.memory.search` -> `kb.memory.delete` lifecycle works.
5. With graph disabled/unavailable, `kb.search` reports vector fallback mode.
6. `kb.search.debug` includes:
   - `filters_effective`, `graph_acl_enforced`, `fusion_mode`
   - `graph_seed_count`, `graph_node_count`, `graph_chunk_bonus_count`, `graph_nonzero`
7. Startup log contains `auto_ingest_started` and one `auto_ingest_cycle`.
8. If graph is enabled and query has structural intent, `graph_nonzero` should be `true` for most cases.

### 12.2 Security

1. Strict mode call without bearer is rejected.
2. Call with valid bearer succeeds.
3. Foreign workspace token cannot read another workspace resource (`error=forbidden`).

### 12.3 Persistence

1. Ingest data.
2. Restart process/containers.
3. Search confirms data is still present.

## 13. Benchmark and KPI Validation

Run:

```bash
python3 bench/run_benchmark.py --top-k 10 --enforce-gates \
  --metadata-dsn sqlite:///./.kb_mcp/bench_metadata_no_rerank.db \
  --output bench/report_no_rerank.json
python3 bench/run_benchmark.py --top-k 10 --rerank --enforce-gates \
  --metadata-dsn sqlite:///./.kb_mcp/bench_metadata_with_rerank.db \
  --output bench/report_with_rerank.json
```

Gates enforced by script:

- `Recall@10 >= 0.85`
- `nDCG@10 >= 0.75`
- `P95 <= 1.5s` (without rerank)
- `P95 <= 3.5s` (with rerank)
- `graph_nonzero_rate >= 0.70` (when candidate graph queries in run >= 10)

Record final values in `docs/kpi_report.md` using `docs/kpi_report_template.md`.

CI benchmark diff:

- workflow: `.github/workflows/benchmark.yml`
- runs base/head benchmark comparison and fails PR on metric regressions.

## 14. Troubleshooting

### Auth failures (`missing_bearer_token`, `invalid_bearer_token`)

- check `KB_AUTH_MODE`;
- verify `Authorization: Bearer <token>` header;
- for `strict`: verify JWT secret/algorithm/claims (`sub`, `workspace_id`);
- for `strict_oauth`: verify `KB_OAUTH_ISSUER_URL`, `KB_OAUTH_JWKS_URL`, `KB_OAUTH_AUDIENCE`, scopes.

### Neo4j degradation / fallback to vector

- verify `KB_NEO4J_URI`, credentials, container health;
- check `kb.search.debug.fallback_mode` and logs;
- restore graph service and retry query.

### Auto-ingest not running or stale

- verify `KB_AUTO_INGEST_ENABLED=true`;
- verify `KB_AUTO_INGEST_ROOTS` paths exist inside runtime (container path, not host path);
- check logs for `auto_ingest_started` and `auto_ingest_cycle`;
- if `failed_roots > 0`, inspect `auto_ingest_root_failed` entries and fix path/permissions;
- inspect `auto_ingest.root_failure` metrics and `auto_ingest_retry` logs for root cause classes;
- tune `KB_AUTO_INGEST_FULL_INTERVAL_CYCLES`, `KB_AUTO_INGEST_RETRY_ATTEMPTS`, `KB_AUTO_INGEST_RETRY_BACKOFF_S`;
- trigger one manual refresh via `kb.ingest.filesystem` for the problematic root.

### Postgres metadata errors

- verify `KB_METADATA_BACKEND=postgres` and DSN syntax;
- apply required schema/table grants;
- confirm connectivity from MCP runtime host/container.

### Embedding provider errors

- for `local`: ensure `sentence-transformers` runtime availability;
- for `openai_compatible`: verify `KB_EMBEDDING_BASE_URL` and API key;
- if provider is unavailable, inspect logs for fallback behavior.

For incident workflows, see `docs/runbook.md`.

## 15. Operational Maintenance

### Backup and restore

- Docker bind mounts: snapshot `.docker-data/qdrant`, `.docker-data/neo4j/data`, `.docker-data/mcp`.
- SQLite metadata: backup the DB file from `.kb_mcp`/mounted path.
- Postgres metadata: use regular `pg_dump`/`pg_restore` procedures.

### Upgrade checklist

1. Backup current data.
2. Review `.env` diffs against new `.env.example`.
3. Pull changes and rebuild (`docker compose up -d --build` or reinstall venv deps).
4. Run smoke checks + benchmark gates.

### Rollback checklist

1. Stop runtime.
2. Restore previous code revision.
3. Restore data snapshot if schema/content changed.
4. Re-run smoke checks and strict auth verification.
