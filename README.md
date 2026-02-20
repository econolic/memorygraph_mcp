# hybrid-kb-mcp

Hybrid Retrieval MCP server for knowledge base + persistent conversation memory.

## Features

- MCP tools: `kb.search`, `kb.graph_expand`, `kb.explain`
- Memory tools: `kb.memory.upsert`, `kb.memory.search`, `kb.memory.delete`
- Ingestion tools: `kb.ingest.filesystem`, `kb.ingest.git_diff`
- Resource URIs: `kb://doc/...`, `kb://chunk/...`, `kb://entity/...`, `kb://memory/...`, `kb://policy/tool-selection`
- Retrieval: vector + graph + always-on cross-encoder rerank (with fallback)
- Security: dual/strict auth modes, JWT-aware identity, deny-by-default ACL, redaction
- Observability: structured logs, audit logger, in-process metrics snapshot
- Ingestion: filesystem + git-diff incremental updates with persisted checksums
- Persistence: metadata/checksums in `sqlite` (default) or `postgres` via DSN

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev,rerank]
```

Run stdio transport:

```bash
python -m kb_mcp.server.transport_stdio
```

Run streamable HTTP transport:

```bash
python -m kb_mcp.server.transport_http
```

Run full local stack:

```bash
cp .env.example .env
mkdir -p .docker-data/qdrant .docker-data/neo4j/data .docker-data/mcp
docker compose up -d --build
```

## Test

```bash
pytest
```

## Notes

- In `dual` mode identity precedence is: `Authorization header` -> `payload.jwt_bearer` -> legacy payload ACL.
- In `strict` mode HTTP requests without valid bearer token are rejected.
- `workspace_id`/`subject` in payload are compatibility fields and can be ignored when auth context is present.
- Memory retention is indefinite by default; use `kb.memory.delete` for subject-level deletion.

## Docker Desktop Persistent Data

This compose setup stores database files on host bind mounts, so data survives container recreation:

- Qdrant: `./.docker-data/qdrant`
- Neo4j: `./.docker-data/neo4j/data`
- MCP metadata/checksums SQLite: `./.docker-data/mcp`

You can override paths in `.env`:

```bash
KB_QDRANT_STORAGE_PATH=/absolute/path/to/qdrant-storage
KB_NEO4J_DATA_PATH=/absolute/path/to/neo4j-data
KB_MCP_DATA_PATH=/absolute/path/to/mcp-data
```

## External DB Connection Mode

To connect MCP container to external/managed Qdrant and Neo4j, set in `.env`:

```bash
KB_QDRANT_URL=http://<qdrant-host>:6333
KB_NEO4J_URI=bolt://<neo4j-host>:7687
KB_NEO4J_USER=<user>
KB_NEO4J_PASSWORD=<password>
KB_METADATA_BACKEND=postgres
KB_METADATA_DSN=postgresql+psycopg://<user>:<password>@<host>:5432/<db>
```

Then run:

```bash
docker compose up -d --build
```

If Postgres permissions are too restrictive for metadata bootstrap, run:

```sql
GRANT USAGE, CREATE ON SCHEMA public TO <user>;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO <user>;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO <user>;
```

## Register In Codex MCP

Add this to `/root/.codex/config.toml`:

```toml
[mcp_servers.hybrid_kb_mcp]
url = "http://127.0.0.1:8080/mcp"
startup_timeout_sec = 60
```

Restart Codex session after updating the config.

## LLM Tool Selection Policy

Use `docs/tool_selection_policy.md` as the canonical instruction set for:

- intent routing (`kb.search` vs `kb.graph_expand` vs `kb.explain`);
- memory workflows (`kb.memory.search|upsert|delete`);
- evidence and citation requirements;
- few-shot examples for orchestrator prompts.

Runtime integration is exposed via:

- prompt: `kb.tool_selection_policy` (system block for agent runtime);
- search trace fields: `intent`, `recommended_tools`, `policy_version`, `auth_mode`, `identity_source` in `kb.search.decision_trace`;
- JSON template: `docs/tool_selection_policy.template.json` for external agent/router configs.

## Benchmark (KPI)

Run offline benchmark corpus with gates:

```bash
python3 bench/run_benchmark.py --top-k 10 --enforce-gates --output bench/report_no_rerank.json
python3 bench/run_benchmark.py --top-k 10 --rerank --enforce-gates --output bench/report_with_rerank.json
```
