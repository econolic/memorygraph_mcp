# KPI Report (Operational Snapshot)

## Release

- Version: 0.1.0
- Date: 2026-02-21
- Evaluator: Codex (local runtime + benchmark artifacts)

## Retrieval Metrics

- Recall@10: 1.0000
- nDCG@10: 0.9929
- MRR: 0.9744
- Dataset size (queries): 156

Source reports:
- `bench/report_no_rerank.json`
- `bench/report_with_rerank.json`

Note:
- Retrieval metrics above come from benchmark artifacts.
- Operational sync metrics below come from live runtime checks on 2026-02-21.

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
- Metadata documents by workspace: `w1=213`, `w_docker=45`, `w_fix_1=1`, `w_fix_2=1`
- Graph documents by workspace: `w1=98` (others absent in graph backend)
- Graph coverage for `w1` (docs in graph / docs in metadata): `98/213 = 0.46`
- Last observed metadata document update for `w1` (UTC): `2026-02-21T19:46:29.634903+00:00`
- Graph signal control suite (10 relation-impact queries): `graph_nonzero_rate = 0.70 (7/10)`
- Runtime evidence:
  - `auto_ingest_started` observed after restart
  - interval cycles observed with `failed_roots=0`
  - multiple cycles observed with `created=0` and `updated=0` (checksum-skip behavior)

## Decision

- Go / No-go: **No-go for graph-sensitive production answers**
- Required follow-ups:
  - Add MCP-level graph sync health contract and expose coverage status to LLM.
  - Add controlled backfill/reindex contract (admin-scoped) for checksum-skip recovery cases.
  - Keep vector-backed answers available, but require low-confidence disclaimer when `graph_nonzero=false` on relation queries.

## Benchmark Commands

```bash
python3 bench/run_benchmark.py --top-k 10 --enforce-gates \
  --metadata-dsn sqlite:///./.kb_mcp/bench_metadata_no_rerank.db \
  --output bench/report_no_rerank.json
python3 bench/run_benchmark.py --top-k 10 --rerank --enforce-gates \
  --metadata-dsn sqlite:///./.kb_mcp/bench_metadata_with_rerank.db \
  --output bench/report_with_rerank.json
```
