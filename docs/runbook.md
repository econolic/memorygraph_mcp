# Runbook

## Health checks

1. Ensure `mcp` process is alive.
2. Check logs for `audit` entries and errors.
3. Verify Qdrant and Neo4j availability.

## Common incidents

### Neo4j unavailable

- Symptom: `fallback_mode=vector` in `kb.search.debug`.
- Action: restore Neo4j connectivity; verify credentials and container health.

### ACL denies all reads

- Symptom: empty results despite known data.
- Action: verify JWT `sub`, `roles`, `workspace_id`; check document `acl_allow` payload.

### Memory pollution risk

- Symptom: low-quality facts in memory.
- Action: increase `KB_MEMORY_CONFIDENCE_THRESHOLD`; enforce stricter citation parser.

## Deletion requests

Use `kb.memory.delete` with `all_for_subject=true` and matching `workspace_id`/`subject`.
