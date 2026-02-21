# KPI Report Template

## Release

- Version:
- Date:
- Evaluator:

## Retrieval Metrics

- Recall@10:
- nDCG@10:
- MRR:
- Dataset size (queries):

## Latency (P95)

- kb.search without rerank:
- kb.search with rerank:

## Filtered Subset Metrics

- Filtered queries:
- Filtered Recall@10:
- Filtered nDCG@10:
- Filtered MRR:
- Filtered citation coverage:
- Filtered P95 latency without rerank:
- Filtered P95 latency with rerank:

## Faithfulness

- Share of claims with evidence (citation coverage):

## Security

- ACL leakage incidents (P0):
- Audit coverage:
- Auth mode tested (`dual|strict`):
- Identity source distribution (`authorization_header|payload_jwt|legacy_acl`):

## Decision

- Go / No-go:
- Required follow-ups:

## Benchmark Commands

Reference guide: `docs/install_deploy_config.md` (section: Benchmark and KPI Validation).

```bash
python3 bench/run_benchmark.py --top-k 10 --enforce-gates \
  --metadata-dsn sqlite:///./.kb_mcp/bench_metadata_no_rerank.db \
  --output bench/report_no_rerank.json
python3 bench/run_benchmark.py --top-k 10 --rerank --enforce-gates \
  --metadata-dsn sqlite:///./.kb_mcp/bench_metadata_with_rerank.db \
  --output bench/report_with_rerank.json
```
