from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from kb_mcp.ingest.entity_index import entity_vector_records
from kb_mcp.retrieval.vector_store import VectorStore
from kb_mcp.storage.metadata_store import MetadataRepository


def backfill_entity_embeddings(
    *,
    metadata: MetadataRepository,
    vector_store: VectorStore,
    workspace_id: str,
    batch_size: int = 128,
) -> dict[str, int | str]:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")

    entities = metadata.list_entities(workspace_id=workspace_id)
    indexed = 0
    skipped = 0
    for offset in range(0, len(entities), batch_size):
        source_batch = entities[offset : offset + batch_size]
        records = entity_vector_records(source_batch)
        skipped += len(source_batch) - len(records)
        vector_store.upsert_entities(entities=records)
        indexed += len(records)
    return {
        "workspace_id": workspace_id,
        "entities_seen": len(entities),
        "indexed": indexed,
        "skipped": skipped,
    }


def main(argv: Sequence[str] | None = None) -> int:
    from kb_mcp.bootstrap import build_deps
    from kb_mcp.config import AppConfig

    parser = argparse.ArgumentParser(
        description="Backfill the persistent entity-embedding index from metadata."
    )
    parser.add_argument("--workspace-id", default=None)
    parser.add_argument("--batch-size", type=int, default=128)
    args = parser.parse_args(argv)

    cfg = AppConfig.from_env()
    deps = build_deps(cfg)
    result = backfill_entity_embeddings(
        metadata=deps.metadata,
        vector_store=deps.vector_store,
        workspace_id=args.workspace_id or cfg.auto_ingest_workspace_id,
        batch_size=args.batch_size,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
