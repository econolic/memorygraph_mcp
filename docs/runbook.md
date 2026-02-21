# Runbook

Primary setup/deployment instructions live in `docs/install_deploy_config.md`.
Use this runbook for live incidents and recovery actions.

## Quick References

- Full deployment and configuration: `docs/install_deploy_config.md`
- Auth hardening and strict mode: `docs/install_deploy_config.md`
- Persistence setup and restart validation: `docs/install_deploy_config.md`
- KPI and benchmark process: `docs/kpi_report_template.md`, `docs/kpi_report.md`

## Health Checks

1. Ensure MCP process/container is running.
2. Check MCP logs for `audit` entries and runtime errors.
3. Verify Qdrant and Neo4j availability.
4. Verify metadata backend connectivity (`sqlite` lock/path or `postgres` DSN).
5. Verify strict auth behavior (`missing_bearer_token` when bearer is absent).
6. Verify startup auto-sync:
   - `auto_ingest_started` appears in logs after restart.
   - `auto_ingest_cycle` appears with `failed_roots=0`.
7. Verify graph signal quality for structural queries:
   - `kb.search.debug.graph_seed_count > 0`
   - `kb.search.debug.graph_nonzero=true` (for most relation-impact queries)
8. If enabled, verify metrics/traces:
   - Prometheus endpoint responds (`/metrics` on configured port)
   - traces appear in configured OTLP backend.

## Common Incidents

### Neo4j unavailable

- Symptom: `fallback_mode=vector` in `kb.search.debug`.
- Actions:
  1. Validate `KB_NEO4J_URI`, `KB_NEO4J_USER`, `KB_NEO4J_PASSWORD`, `KB_NEO4J_DATABASE`.
  2. Check Neo4j container/service health.
  3. Re-run search and confirm fallback is cleared.
  4. Confirm `kb.search.debug.graph_acl_enforced=true` unless explicitly disabled.
  5. Confirm `kb.search.debug.graph_seed_count` and `kb.search.debug.graph_nonzero` recover.

### Strict mode auth rejects calls

- Symptom: `missing_bearer_token` / `invalid_bearer_token`.
- Actions:
  1. Ensure request has `Authorization: Bearer <token>`.
  2. Verify JWT has `sub` and `workspace_id`.
  3. If `KB_AUTH_MODE=strict`, verify `KB_JWT_SECRET` and algorithm match issuer.
  4. If `KB_AUTH_MODE=strict_oauth`, verify `KB_OAUTH_ISSUER_URL`, `KB_OAUTH_JWKS_URL`, `KB_OAUTH_AUDIENCE`, and required scopes.
  5. If needed during migration, switch to `KB_AUTH_MODE=dual` temporarily.
  6. Re-run smoke from `./scripts/smoke_strict_oauth.sh` to isolate config issues.

### ACL denies expected reads

- Symptom: empty search/resource results despite known data.
- Actions:
  1. Verify JWT identity (`sub`, `roles`, `workspace_id`).
  2. Verify `acl_allow` metadata on doc/chunk/entity/memory.
  3. Confirm no payload spoof mismatch (`decision_trace.identity_source`).
  4. Inspect `kb.search.debug.filters_effective` and verify `tags/sources/updated_after`.

### Postgres metadata permission failures

- Symptom: metadata tables not created or write failures.
- Actions:
  1. Validate `KB_METADATA_BACKEND=postgres` and `KB_METADATA_DSN`.
  2. Apply schema/table grants from `docs/install_deploy_config.md`.
  3. Restart MCP service and confirm metadata initialization succeeds.

### Memory quality degradation

- Symptom: low-quality or noisy facts in `kb.memory.search`.
- Actions:
  1. Increase `KB_MEMORY_CONFIDENCE_THRESHOLD`.
  2. Enforce citation quality during `kb.memory.upsert`.
  3. Delete invalid memory entries by `ids` or `all_for_subject=true`.

### Benchmark regression

- Symptom: `bench/run_benchmark.py --enforce-gates` fails.
- Actions:
  1. Run benchmark without gates and inspect raw metrics.
  2. Compare no-rerank vs rerank reports.
  3. Verify ingestion freshness and stale chunk cleanup.
  4. Compare filtered subset metrics (`filtered_recall_at_10`, `filtered_ndcg_at_10`).
  5. Inspect `graph_nonzero_rate` for structural-query regressions.

### Auto-ingest lag or stopped updates

- Symptom: project changed but retrieval still serves old chunks.
- Actions:
  1. Check `KB_AUTO_INGEST_ENABLED`, `KB_AUTO_INGEST_ROOTS`, `KB_AUTO_INGEST_INTERVAL_S`.
  2. Validate root paths from runtime perspective (container vs host paths).
  3. Check logs for `auto_ingest_cycle` and `auto_ingest_root_failed`.
  4. Check retry signals: `auto_ingest_retry` logs and metric `kb_auto_ingest_root_failures_total`.
  5. Tune `KB_AUTO_INGEST_FULL_INTERVAL_CYCLES`, `KB_AUTO_INGEST_GIT_SINCE_REF`, retry/backoff envs.
  6. Run one manual `kb.ingest.filesystem` call for affected root.
  7. If needed, restart MCP and confirm new startup cycle logs.

## Persistence Recovery

If data appears lost after restart:

1. Confirm bind mounts are still mapped:
   - `./.docker-data/qdrant`
   - `./.docker-data/neo4j/data`
   - `./.docker-data/mcp`
2. Confirm `.env` paths were not changed unexpectedly.
3. Validate metadata backend selection (`sqlite` vs `postgres`).
4. Re-run minimal search and resource read checks with valid bearer.

## Deletion Requests

Use `kb.memory.delete` with `all_for_subject=true` and matching `workspace_id`/`subject`.
