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

## Common Incidents

### Neo4j unavailable

- Symptom: `fallback_mode=vector` in `kb.search.debug`.
- Actions:
  1. Validate `KB_NEO4J_URI`, `KB_NEO4J_USER`, `KB_NEO4J_PASSWORD`, `KB_NEO4J_DATABASE`.
  2. Check Neo4j container/service health.
  3. Re-run search and confirm fallback is cleared.

### Strict mode auth rejects calls

- Symptom: `missing_bearer_token` / `invalid_bearer_token`.
- Actions:
  1. Ensure request has `Authorization: Bearer <jwt>`.
  2. Verify JWT has `sub` and `workspace_id`.
  3. Verify `KB_JWT_SECRET` and algorithm match issuer.
  4. If needed during migration, switch to `KB_AUTH_MODE=dual` temporarily.

### ACL denies expected reads

- Symptom: empty search/resource results despite known data.
- Actions:
  1. Verify JWT identity (`sub`, `roles`, `workspace_id`).
  2. Verify `acl_allow` metadata on doc/chunk/entity/memory.
  3. Confirm no payload spoof mismatch (`decision_trace.identity_source`).

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
