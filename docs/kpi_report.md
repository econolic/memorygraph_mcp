# KPI Report

## Release

- Version: 0.1.0
- Date: 2026-02-21
- Evaluator: Codex (local runtime benchmark)

## Retrieval Metrics

- Recall@10: 1.0000
- nDCG@10: 0.9929
- MRR: 0.9744
- Dataset size (queries): 156

Source reports:
- `bench/report_no_rerank.json`
- `bench/report_with_rerank.json`

## Latency (P95)

- kb.search without rerank: 9.67 ms
- kb.search with rerank: 10.39 ms

## Filtered Subset Metrics

- Filtered queries: 6
- Filtered Recall@10: 1.0000
- Filtered nDCG@10: 1.0000
- Filtered MRR: 1.0000
- Filtered Citation coverage: 1.0000
- Filtered P95 latency without rerank: 4.99 ms
- Filtered P95 latency with rerank: 5.93 ms

## Faithfulness

- Citation coverage: 1.0000

## Security

- ACL leakage incidents (P0): 0
  - Source: strict auth/ACL integration checks in `tests/test_http_auth_resources_acl.py` and local strict-mode acceptance run.
- Audit coverage: MCP tool calls audited (`kb.search`, `kb.graph_expand`, `kb.explain`, `kb.memory.*`, `kb.ingest.*`)
- Auth mode tested: strict
- Identity source distribution (observed in strict HTTP integration + acceptance):
  - `authorization_header`: observed
  - `payload_jwt`: not observed
  - `legacy_acl`: not observed (strict mode)

## Operational Sync

- Auto-ingest enabled: true
- Auto-ingest startup cycle observed: true
- Auto-ingest interval: 900 seconds
- Indexed coverage for `project_sync`: 81/81
- Indexed coverage for `project_delta`: 34/34
- Last observed document update timestamp (UTC): `2026-02-21T17:37:37.134004+00:00`
- Runtime evidence:
  - `auto_ingest_started` log at `2026-02-21T17:37:23.572889+00:00`
  - `auto_ingest_cycle` startup log at `2026-02-21T17:37:44.095641+00:00` (`created=1`, `updated=3`, `failed_roots=0`)

## Decision

- Go / No-go: **Go**
- Required follow-ups:
  - Add larger multilingual benchmark slice (RU+EN) to validate cross-lingual retrieval at 300+ queries.
  - Calibrate benchmark-diff CI thresholds after first 3 PR runs with real variance.

## Benchmark Commands

```bash
python3 bench/run_benchmark.py --top-k 10 --enforce-gates \
  --metadata-dsn sqlite:///./.kb_mcp/bench_metadata_no_rerank.db \
  --output bench/report_no_rerank.json
python3 bench/run_benchmark.py --top-k 10 --rerank --enforce-gates \
  --metadata-dsn sqlite:///./.kb_mcp/bench_metadata_with_rerank.db \
  --output bench/report_with_rerank.json
```
