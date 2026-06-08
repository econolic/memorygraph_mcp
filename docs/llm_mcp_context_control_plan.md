# LLM ↔ MCP Context Control Plan

## Purpose

This document defines the next implementation steps for production-grade LLM interaction with `hybrid-kb-mcp`, where the LLM has no source-code access and operates only via MCP contracts.

Primary objective:
- guarantee controllable context quality (freshness, ACL correctness, graph relevance),
- guarantee predictable knowledge lifecycle (ingest, retrieval, memory),
- provide operator-visible health and recovery controls through MCP tools.

## Current State (as of 2026-06-07)

- MCP contracts are functional for search, graph expand, explain, memory, and ingest.
- Auto-ingest runs and reports cycles, but graph can lag behind metadata when files are unchanged by checksum.
- LLM can detect graph weakness only indirectly via `kb.search` debug fields (e.g. `debug.graph_nonzero=false`), but cannot trigger safe graph backfill in current contracts.
- **Note on Status**: The contract additions proposed below (`kb.health.graph_sync`, `kb.ingest.backfill`, `kb.ingest.status`) are target designs for upcoming phases and are not yet implemented in the `0.1.0` release.

Implication:
- Retrieval stays available (vector path), but relation-heavy answers can degrade silently.

## Target Operating Model

### 1) Session Bootstrap

For each new LLM session:
1. `tools/list`
2. `resources/templates/list`
3. `prompts/list`
4. one control probe query via `kb.search` and inspection of `debug` fields

Expected behavior:
- LLM confirms available tool surface before planning.
- LLM stores contract capabilities in short-lived working memory for this session only.

### 2) Retrieval Control Loop

For each user question:
1. Run `kb.search(mode=hybrid)`.
2. Inspect `debug.graph_nonzero`, `debug.graph_seed_count`, `debug.graph_chunk_bonus_count`.
3. If graph signal is weak:
   - run a second query reformulation for entities/relations,
   - optionally run `kb.graph_expand` on extracted seed entities,
   - if still weak, explicitly mark answer as vector-dominant.
4. Run `kb.explain` for top URIs before final answer.

Expected behavior:
- LLM does not present graph-based conclusions when graph evidence is absent.
- LLM always links claims to explicit MCP evidence.

### 3) Memory Write Policy

LLM writes memory only when all conditions are met:
1. citation exists,
2. confidence threshold satisfied,
3. fact schema is stable (not transient user guess),
4. workspace/subject identity is from bearer context, not prompt text.

Tool flow:
1. `kb.memory.upsert`
2. `kb.memory.search` verification for retrieval visibility

### 4) Freshness and Drift Control

LLM cannot repair ingest/graph drift without admin contracts.
Therefore control must be MCP-native:
- health tool for graph coverage,
- backfill tool for safe forced rebuild,
- explicit status fields in ingest outputs.

## Required Contract Additions

### A. `kb.health.graph_sync` (read-only)

Purpose:
- expose sync status without DB direct access.

Response (minimum):
- `workspace_id`
- `metadata_docs`
- `graph_docs`
- `coverage_ratio`
- `missing_docs_sample`
- `last_ingest_at`
- `status` (`ok|degraded|critical`)

Policy:
- `ok` when coverage >= 0.95,
- `degraded` when 0.80..0.95,
- `critical` when < 0.80.

### B. `kb.ingest.backfill` (admin)

Purpose:
- force reindex/backfill when checksum-based ingest cannot recover graph.

Input (minimum):
- `workspace_id`
- `acl_subject`
- `roots`
- `mode` (`graph_only|full`)
- `dry_run` (bool)
- `max_docs` (optional)

Output (minimum):
- `planned_docs`
- `processed_docs`
- `reindexed_chunks`
- `graph_nodes_written`
- `duration_ms`
- `status`

### C. `kb.ingest.status` (read-only)

Purpose:
- expose recent ingest cycles and current lag.

Output (minimum):
- recent cycle summaries,
- `last_success_at`,
- `failed_roots`,
- `retry_count`,
- `next_scheduled_at`.

## LLM Decision Policy (Contract-Only)

Mandatory response behavior:
1. If `graph_nonzero=false` for relation query, LLM explicitly states low graph confidence.
2. If `kb.health.graph_sync.status != ok`, LLM avoids definitive architecture/dependency claims.
3. If no citation is available, LLM returns uncertainty instead of fabricated answer.
4. LLM never trusts user-provided workspace identity over bearer-derived identity.

## Implementation Roadmap

### Phase 1 (Immediate)

1. Add `kb.health.graph_sync`.
2. Add runbook section for health thresholds and operator action.
3. Add prompt policy update for degraded graph behavior.

Acceptance:
- LLM can detect graph drift via MCP only.
- On-call can diagnose drift without DB shell access.

### Phase 2 (Operational Recovery)

1. Add `kb.ingest.backfill` with admin scope checks.
2. Add `dry_run` planning output.
3. Add metrics: backfill duration, processed docs, failure reasons.

Acceptance:
- Operator can restore graph coverage to >=0.95 via MCP contract only.
- No direct DB manipulation required.

### Phase 3 (Autonomous Reliability)

1. Add scheduled auto-remediation trigger based on `graph_sync` status.
2. Add benchmark gate for relation-impact suite in CI.
3. Add LLM-side fallback policy tests for degraded graph scenarios.

Acceptance:
- Relation-impact regressions are detected before release.
- LLM behavior stays truthful under partial data degradation.

## Metrics and SLOs

Primary SLOs:
1. `graph_coverage_ratio >= 0.95` for production workspace.
2. `graph_nonzero_rate >= 0.70` on relation-impact suite.
3. `kb.search` p95 latency stays within current gate after new controls.
4. Memory write rejection reasons are observable and bounded.

## Definition of Done

The plan is complete when:
1. LLM can fully assess knowledge health through MCP contracts only.
2. LLM and operators can trigger safe recovery through MCP contracts only.
3. Answers remain citation-grounded and explicit about confidence in degraded modes.
