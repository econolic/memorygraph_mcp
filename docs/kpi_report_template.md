# KPI Report Template

## Release

- Version:
- Date:
- Evaluator:
- Deployment class (`local-dev|self-hosted-internal|self-hosted-behind-proxy`):
- Runtime profile (`docker-compose.yml|docker-compose.selfhosted.yml|source`):
- Auth mode used for release gate:
- Benchmark corpus / dataset version:

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
- Graph signal candidate queries:
- Graph signal nonzero queries:
- Graph nonzero rate:

## Faithfulness

- Share of claims with evidence (citation coverage):

## Security

- ACL leakage incidents (P0):
- Audit coverage:
- Auth mode tested (`dual|strict|strict_oauth`):
- Identity source distribution (`authorization_header|payload_jwt|legacy_acl`):

## Operational Sync

- Auto-ingest enabled (`true|false`):
- Auto-ingest startup cycle observed (`true|false`):
- Auto-ingest interval (seconds):
- Metadata documents by workspace:
- Graph documents by workspace:
- Graph coverage for target workspace (graph_docs/metadata_docs):
- Last observed document update timestamp for target workspace (UTC):
- Graph signal control suite (`graph_nonzero_rate`, nonzero/total):

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
