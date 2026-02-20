from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from kb_mcp.bootstrap import build_deps  # noqa: E402
from kb_mcp.config import AppConfig  # noqa: E402
from kb_mcp.retrieval.rerank import RerankConfig  # noqa: E402


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        item = json.loads(line)
        if isinstance(item, dict):
            out.append(item)
    return out


def _recall_at_k(relevant: set[str], ranked: list[str], k: int) -> float:
    if not relevant:
        return 0.0
    top = ranked[:k]
    return len(relevant.intersection(top)) / len(relevant)


def _dcg(relevant: set[str], ranked: list[str], k: int) -> float:
    value = 0.0
    for idx, item in enumerate(ranked[:k], start=1):
        gain = 1.0 if item in relevant else 0.0
        value += gain / (1.0 if idx == 1 else math.log2(idx))
    return value


def _ndcg_at_k(relevant: set[str], ranked: list[str], k: int) -> float:
    ideal = list(relevant)
    idcg = _dcg(relevant, ideal, k)
    if idcg == 0:
        return 0.0
    return _dcg(relevant, ranked, k) / idcg


def _mrr(relevant: set[str], ranked: list[str]) -> float:
    for idx, item in enumerate(ranked, start=1):
        if item in relevant:
            return 1.0 / idx
    return 0.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", default="bench/corpus")
    parser.add_argument("--queries", default="bench/queries.jsonl")
    parser.add_argument("--relevance", default="bench/relevance.jsonl")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--workspace-id", default="bench")
    parser.add_argument("--subject", default="bench_user")
    parser.add_argument("--vector-backend", default="memory")
    parser.add_argument("--graph-backend", default="memory")
    parser.add_argument("--metadata-backend", default="sqlite")
    parser.add_argument("--metadata-dsn", default="sqlite:///./.kb_mcp/bench_metadata.db")
    parser.add_argument("--rerank", action="store_true")
    parser.add_argument("--enforce-gates", action="store_true")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    base_cfg = AppConfig.from_env()
    cfg = replace(
        base_cfg,
        vector_backend=args.vector_backend,
        graph_backend=args.graph_backend,
        metadata_backend=args.metadata_backend,
        metadata_dsn=args.metadata_dsn,
    )
    if cfg.metadata_backend == "sqlite" and cfg.metadata_dsn.startswith("sqlite:///"):
        sqlite_path = Path(cfg.metadata_dsn.removeprefix("sqlite:///"))
        if sqlite_path.exists():
            sqlite_path.unlink()

    deps = build_deps(cfg)
    deps.ingestion.ingest_filesystem(
        root=args.corpus,
        workspace_id=args.workspace_id,
        acl_allow=[args.subject],
    )

    queries = _read_jsonl(Path(args.queries))
    relevance_rows = _read_jsonl(Path(args.relevance))
    relevance = {str(row["qid"]): set(str(v) for v in row.get("expected_sources", [])) for row in relevance_rows}

    recalls: list[float] = []
    ndcgs: list[float] = []
    mrrs: list[float] = []
    citation_cov: list[float] = []
    latencies_ms: list[float] = []

    for row in queries:
        qid = str(row["qid"])
        query = str(row["query"])
        t0 = time.perf_counter()
        items, _debug = deps.retriever.search(
            query=query,
            top_k=args.top_k,
            filters={"workspace_id": args.workspace_id, "acl_subject": args.subject},
            depth=2,
            edge_types=[],
            max_nodes=200,
            rerank=RerankConfig(enabled=args.rerank, top_n=args.top_k),
        )
        latencies_ms.append((time.perf_counter() - t0) * 1000.0)

        ranked_sources: list[str] = []
        cited = 0
        for item in items:
            chunk = deps.metadata.get_chunk(item.uri)
            if chunk is None:
                continue
            source_path = str(chunk.get("source_path", ""))
            ranked_sources.append(Path(source_path).name)
            evidence = deps.evidence.build(uri=item.uri, score=item.score, breakdown=item.score_breakdown)
            if evidence.citations:
                cited += 1

        rel = relevance.get(qid, set())
        recalls.append(_recall_at_k(rel, ranked_sources, args.top_k))
        ndcgs.append(_ndcg_at_k(rel, ranked_sources, args.top_k))
        mrrs.append(_mrr(rel, ranked_sources))
        citation_cov.append(float(cited) / max(1.0, float(len(items))))

    p95 = statistics.quantiles(latencies_ms, n=100)[94] if len(latencies_ms) > 1 else (latencies_ms[0] if latencies_ms else 0.0)
    report = {
        "queries": len(queries),
        "top_k": args.top_k,
        "rerank_enabled": args.rerank,
        "recall_at_10": sum(recalls) / max(1, len(recalls)),
        "ndcg_at_10": sum(ndcgs) / max(1, len(ndcgs)),
        "mrr": sum(mrrs) / max(1, len(mrrs)),
        "faithfulness_proxy_citation_coverage": sum(citation_cov) / max(1, len(citation_cov)),
        "p95_latency_ms": p95,
    }

    if args.output:
        Path(args.output).write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, indent=2))

    if args.enforce_gates:
        failures: list[str] = []
        if report["recall_at_10"] < 0.85:
            failures.append("recall_at_10 < 0.85")
        if report["ndcg_at_10"] < 0.75:
            failures.append("ndcg_at_10 < 0.75")
        if args.rerank and report["p95_latency_ms"] > 3500:
            failures.append("p95_latency_ms > 3500 with rerank")
        if not args.rerank and report["p95_latency_ms"] > 1500:
            failures.append("p95_latency_ms > 1500 without rerank")
        if failures:
            print(json.dumps({"gate_failures": failures}, ensure_ascii=True, indent=2))
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
