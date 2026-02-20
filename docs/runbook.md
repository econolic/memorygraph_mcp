# Runbook

## Health checks

1. Ensure `mcp` process is alive.
2. Check logs for `audit` entries and errors.
3. Verify Qdrant and Neo4j availability.
4. Verify metadata backend connectivity (`sqlite` file lock or `postgres` DSN).

## Common incidents

### Neo4j unavailable

- Symptom: `fallback_mode=vector` in `kb.search.debug`.
- Action: restore Neo4j connectivity; verify credentials and container health.

### Strict mode auth rejects calls

- Symptom: tool call returns `missing_bearer_token` / `invalid_bearer_token`.
- Action:
  1. Ensure HTTP request has `Authorization: Bearer <jwt>`.
  2. Verify JWT has `sub` and `workspace_id`.
  3. For temporary compatibility use `KB_AUTH_MODE=dual`.

### ACL denies all reads

- Symptom: empty results despite known data.
- Action:
  1. Verify JWT `sub`, `roles`, `workspace_id`.
  2. Verify `acl_allow` metadata for doc/chunk/entity/memory.
  3. Verify no payload spoofing mismatch (`identity_source` in `decision_trace`).

### Memory pollution risk

- Symptom: low-quality facts in memory.
- Action: increase `KB_MEMORY_CONFIDENCE_THRESHOLD`; enforce stricter citation parser.

### Benchmark regression

- Symptom: `bench/run_benchmark.py --enforce-gates` fails.
- Action:
  1. Run without gates and inspect output JSON (`recall_at_10`, `ndcg_at_10`, `mrr`, `p95_latency_ms`).
  2. Re-run with `--rerank` and compare deltas.
  3. Inspect ingestion freshness (`kb.ingest.git_diff`) and stale chunk cleanup.

## Deletion requests

Use `kb.memory.delete` with `all_for_subject=true` and matching `workspace_id`/`subject`.
