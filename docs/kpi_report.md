# KPI Report

## Release

- Version: 0.1.0
- Date: 2026-02-20
- Evaluator: Codex (local runtime benchmark)

## Retrieval Metrics

- Recall@10: 1.0000
- nDCG@10: 0.9926
- MRR: 0.9733
- Dataset size (queries): 150

Source reports:
- `bench/report_no_rerank.json`
- `bench/report_with_rerank.json`

## Latency (P95)

- kb.search without rerank: 2.85 ms
- kb.search with rerank: 4.14 ms

## Faithfulness

- Citation coverage: 1.0000

## Security

- ACL leakage incidents (P0): 0
  - Source: strict E2E acceptance report `bench/acceptance_e2e_strict_report_fixed.json` (`FAILED=[]`)
- Audit coverage: MCP tool calls audited (`kb.search`, `kb.graph_expand`, `kb.explain`, `kb.memory.*`, `kb.ingest.*`)
- Auth mode tested: strict
- Identity source distribution (observed in strict HTTP integration + acceptance):
  - `authorization_header`: observed
  - `payload_jwt`: not observed
  - `legacy_acl`: not observed (strict mode)

## Decision

- Go / No-go: **Go**
- Required follow-ups:
  - Add larger multilingual benchmark slice (RU+EN) to validate cross-lingual retrieval at 300+ queries.
  - Add CI step to publish benchmark diff against previous release.

## Benchmark Commands

```bash
python3 bench/run_benchmark.py --top-k 10 --enforce-gates --output bench/report_no_rerank.json
python3 bench/run_benchmark.py --top-k 10 --rerank --enforce-gates --output bench/report_with_rerank.json
```
