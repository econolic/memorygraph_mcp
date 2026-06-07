# hybrid-kb-mcp

Hybrid Retrieval MCP server for knowledge base retrieval and persistent conversation memory.

## What This Project Provides

- MCP tools: `kb.health`, `kb.route`, `kb.search`, `kb.graph_expand`, `kb.explain`
- Memory tools: `kb.memory.upsert`, `kb.memory.search`, `kb.memory.delete`
- Ingestion tools: `kb.ingest.filesystem`, `kb.ingest.git_diff`
- ACL-protected resources: `kb://doc/*`, `kb://chunk/*`, `kb://entity/*`, `kb://memory/*`,
  `kb://policy/tool-selection`
- MCP prompts: `kb.answer_with_citations`, `kb.tool_selection_policy`,
  `kb.incident_triage`, `kb.memory_grounded_reply`
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
- `kb.health`: return read-only runtime health/config surface without secrets.
- `kb.route`: return intent + recommended tools + execution plan (no client-side guessing).
- `kb.graph_expand`: show entity relations, dependency chains, and impact paths.
- `kb.explain`: explain why retrieved results are relevant.
- `kb.memory.upsert`: save confirmed facts/decisions/preferences for a user/workspace.
- `kb.memory.search`: retrieve previously saved user/workspace context.
- `kb.memory.delete`: delete saved memory by IDs or all memory for a subject.
- `kb.ingest.filesystem`: ingest knowledge from a folder (full scan with incremental updates).
- `kb.ingest.git_diff`: ingest only files changed in git diff (faster incremental refresh).

## MCP Contract Surface

All typed tool outputs include additive contract fields while preserving legacy fields:

- `ok`: boolean success marker.
- `error_code`: one of `VALIDATION_ERROR`, `NOT_FOUND`, `PERMISSION_DENIED`, `TIMEOUT`,
  `UPSTREAM_UNAVAILABLE`, `CONFLICT`, `UNKNOWN_ERROR`, or `null`.
- `error_detail`: short model-readable error detail, or `null`.
- `meta`: operational metadata such as `latency_ms`, `request_id`, or policy version.

Compatibility notes:

- Existing fields such as `results`, `stored_ids`, `created`, `updated`, and resource
  `error: "forbidden"` are kept.
- Strict HTTP auth failures still return MCP tool execution errors (`isError: true`) instead of
  soft `ok=false` payloads.
- Ingestion tools are privileged side-effecting tools. They enforce `KB_INGEST_ALLOWED_ROOTS`
  and support `dry_run=true`.

| Tool | Side effects | Risk | Notes |
|---|---:|---|---|
| `kb.health` | no | Low | Runtime status, no secrets |
| `kb.route` | no | Low | Router-first plan |
| `kb.search` | no | Low | Retrieval + citations |
| `kb.graph_expand` | no | Low | Graph expansion |
| `kb.explain` | no | Low | Relevance reasons |
| `kb.memory.search` | no | Low | Subject/workspace-scoped reads |
| `kb.memory.upsert` | yes | Medium | Requires validated citations/confidence |
| `kb.memory.delete` | yes | High | Deletes subject/workspace memory |
| `kb.ingest.filesystem` | yes | High | Root must be in `KB_INGEST_ALLOWED_ROOTS`; supports `dry_run` |
| `kb.ingest.git_diff` | yes | High | Root must be in `KB_INGEST_ALLOWED_ROOTS`; supports `dry_run` |

## Documentation Map

- Full install/deploy/config guide: `docs/install_deploy_config.md`
- Operational incident handling: `docs/runbook.md`
- LLM tool routing policy: `docs/tool_selection_policy.md`
- LLM↔MCP context control roadmap: `docs/llm_mcp_context_control_plan.md`
- KPI template: `docs/kpi_report_template.md`
- Current KPI report: `docs/kpi_report.md`
- Contribution guide: `CONTRIBUTING.md`
- Security policy: `SECURITY.md`

## Support Scope

Supported (default project target):

- Local development (`stdio` or HTTP on localhost)
- Self-hosted internal/protected network deployments
- Self-hosted deployments behind a reverse proxy with TLS and hardening

Not supported by default:

- Public SaaS / direct internet-facing multi-tenant service
- Managed platform responsibilities (WAF, abuse controls, tenant quotas, billing, compliance ops)

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

Hardened self-hosted profile (recommended baseline for non-dev deployments):

```bash
cp .env.selfhosted.example .env
docker compose -f docker-compose.selfhosted.yml up -d --build
```

Notes:

- `docker-compose.yml` is the local/dev quickstart profile.
- `docker-compose.selfhosted.yml` is the production-oriented self-hosted profile (DB ports internal-only by default).

## MCP Endpoint

- HTTP MCP: `http://127.0.0.1:8080/mcp`
- Stdio entrypoint: `python -m kb_mcp.server.transport_stdio`

Minimal HTTP health check through MCP JSON-RPC:

```bash
curl -sS http://127.0.0.1:8080/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{"jsonrpc":"2.0","id":"health","method":"tools/call","params":{"name":"kb.health","arguments":{}}}'
```

Expected `structuredContent` shape:

```json
{
  "ok": true,
  "service_name": "hybrid-kb-mcp",
  "auth_mode": "strict",
  "backends": {"vector": "qdrant", "graph": "neo4j", "metadata": "sqlite"},
  "tools": ["kb.health", "kb.route", "kb.search"]
}
```

## Route Wrapper (Client-Side)

The repo includes a client wrapper that tries `kb.route` first and then executes the returned
`execution_plan` (`kb.memory.search` / `kb.search` / `kb.graph_expand` / `kb.explain`).
If `kb.route` is unavailable on the connected server, the wrapper falls back to a compatibility
plan (`kb.memory.search` + `kb.search`).

HTTP mode (the wrapper currently requires a bearer token; this is mandatory for strict/strict_oauth servers):

```bash
TOKEN="<jwt_or_access_token>"
./scripts/kb_route_wrapper.py --transport http --token "$TOKEN" "Какие зависимости у сервиса X?"
```

Stdio mode (starts local MCP server process automatically):

```bash
./scripts/kb_route_wrapper.py --transport stdio --stdio-disable-auto-ingest "Какие зависимости у сервиса X?"
```

Notes:

- `stdio` mode launches `kb_mcp.server.transport_stdio` from this repo's `.venv` by default.
- first stdio run may be noticeably slower due to cold start/imports.
- `--allow-memory-delete` is required for executing `kb.memory.delete` steps.

## Security Notes

- Use `KB_AUTH_MODE=strict` for JWT deployments, or `KB_AUTH_MODE=strict_oauth` for OIDC/JWKS deployments.
- In `dual` mode precedence is:
  - `Authorization` header -> `payload.jwt_bearer` -> legacy payload ACL.
- In `strict_oauth` mode, HTTP requests require `Authorization: Bearer ...`; token is validated against OIDC JWKS.
- HTTP transport supports Host/Origin restrictions via `KB_TRANSPORT_ALLOWED_HOSTS` and `KB_TRANSPORT_ALLOWED_ORIGINS`.
- Graph retrieval enforces object ACL by default (`KB_GRAPH_ENFORCE_OBJECT_ACL=true`).
- Startup now rejects weak/placeholder JWT secrets in unsafe modes (e.g. `strict`, or `dual` with non-localhost HTTP bind).

## Production Readiness Checklist (Self-Hosted)

Before using this project outside local/dev:

1. Set `KB_AUTH_MODE=strict` or `KB_AUTH_MODE=strict_oauth`.
2. Replace all placeholder secrets/passwords (`KB_JWT_SECRET`, Neo4j/Postgres credentials).
3. Put MCP behind a reverse proxy with TLS (HTTPS) and request limits.
4. Keep Qdrant/Neo4j/Postgres on internal network only (no public exposure by default).
5. Verify persistence and backups for `.docker-data/*` or external DBs.
6. Run `./scripts/release_selfhosted_smoke.sh`.
7. Run benchmark gates (`bench/run_benchmark.py --enforce-gates`) and record results in `docs/kpi_report.md`.
8. Enable monitoring where needed (`KB_PROMETHEUS_ENABLED`, `KB_OTEL_ENABLED`).

## Public SaaS / Internet-Facing Risks

This repository is an OSS **self-hosted** MCP server, not a managed SaaS platform.

If you expose it directly to the public internet or operate it as multi-tenant SaaS, you must additionally build and operate:

- TLS termination and certificate lifecycle management at the edge
- reverse proxy hardening (Origin policy enforcement, request size limits, timeouts)
- rate limiting, abuse prevention, and DoS controls
- WAF / bot mitigation where applicable
- secret management and rotation (not `.env` files alone)
- stronger tenant isolation verification beyond current app-level ACL checks
- quotas, noisy-neighbor controls, and service-level admission controls
- compliance/privacy operations (audit retention, PII handling, deletion workflows)
- HA/failover/backup restore drills and on-call/SLO operations
- dependency/CVE monitoring and patch rollout process

For self-hosted production guidance, see `docs/install_deploy_config.md`.

## Bearer Token Setup for MCP Clients

If auth mode is `strict` or `strict_oauth`, MCP calls require bearer auth on every request.

Get bearer in `strict` mode (JWT):

```bash
set -a; source .env; set +a
TOKEN="$(python3 - <<'PY'
import os, jwt
print(jwt.encode({"sub":"u1","workspace_id":"w1","roles":["reader"]}, os.environ["KB_JWT_SECRET"], algorithm="HS256"))
PY
)"
export HYBRID_KB_MCP_AUTH_HEADER="Bearer ${TOKEN}"
```

Get bearer in `strict_oauth` mode:

- use your IdP/issuer flow to mint access token;
- then export header value:

```bash
export HYBRID_KB_MCP_AUTH_HEADER="Bearer <access_token>"
```

Codex MCP config example (`/root/.codex/config.toml`):

```toml
[mcp_servers.hybrid_kb_mcp]
url = "http://127.0.0.1:8080/mcp"
startup_timeout_sec = 60
env_http_headers = { Authorization = "HYBRID_KB_MCP_AUTH_HEADER" }
```

After updating token/config, restart MCP client session.

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
  - `KB_INGEST_ALLOWED_ROOTS` (comma-separated resolved allowlist; defaults to `KB_AUTO_INGEST_ROOTS`)
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

## Scalability and Parallel Usage

Current default profile (`docker compose` with local bind mounts) is viable for local/dev and small-team runtime:

- data is persistent on host (`.docker-data/*`);
- MCP, Qdrant, and Neo4j run as single-host services;
- good for moderate concurrent read/search traffic.

For larger production-scale and stronger parallel usage, move to shared external services:

- use external/managed Qdrant and Neo4j (clustered/HA topology);
- use Postgres metadata backend instead of local SQLite;
- run MCP as stateless replicas behind a load balancer;
- keep ingestion controlled (single-writer/queue/leader) to avoid write races.

Bottom line:

- current model is operationally valid for small-to-medium deployments;
- for high-scale multi-tenant workloads, use external DB architecture and horizontal MCP scaling.

## Benchmark Commands

Fast local readiness gate:

```bash
make install-dev
make check-fast
```

Direct equivalent:

```bash
.venv/bin/python -m pip install -e .[dev,rerank]
.venv/bin/ruff check .
.venv/bin/python -m mypy kb_mcp
.venv/bin/python -m pytest -q -m "not docker and not benchmark and not external"
```

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

## Self-Hosted Release Smoke

Reproducible strict-mode self-hosted smoke:

```bash
cp .env.selfhosted.example .env
./scripts/release_selfhosted_smoke.sh
```

What it checks (baseline):

- `tools/list`, `kb.health`, `kb.route`, `kb.search`
- ingestion + citations
- wrapper (`kb.route` + `execution_plan`)
- memory lifecycle (`upsert/search/delete`)
- resource ACL deny with foreign workspace token
- persistence across MCP restart
