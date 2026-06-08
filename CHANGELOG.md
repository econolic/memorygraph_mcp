# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Strategy query router (`kb.route` tool) to automatically plan tool execution and detect query intent.
- Multilingual embedding preset support with query/passage prefixing and caching.
- Dynamic query expansion via semantic entity enrichment.
- Resiliency Middlewares: rate limiting (token bucket per workspace/subject) and circuit breaker.
- Destructive confirmation gate for `kb.memory.delete` to protect against accidental deletions.
- Idempotency key support for `kb.memory.upsert` tool calls.
- Enhanced test suite in `tests/test_enhanced_features.py` validating router, resiliency, and confirmation gates.
- Self-hosted production-oriented Docker Compose profile and environment template.
- OSS project governance artifacts (`SECURITY.md`, `CONTRIBUTING.md`, issue/PR templates).
- CI workflow for lint/type/tests and a separate dependency/security scan workflow.
- Release smoke script for self-hosted strict-mode validation.

### Changed
- Startup security validation rejects weak JWT secrets in unsafe modes.
- README/docs now explicitly scope support to self-hosted deployments and list Public SaaS risks.

## [0.1.0] - 2026-02-24

### Added
- Hybrid Retrieval MCP server with vector + graph retrieval, memory tools, ingestion tools, ACL, and HTTP/stdio transports.
- Docker Compose local stack (Qdrant + Neo4j + MCP).
- Benchmark harness and benchmark-diff CI workflow.
- Deployment and runbook documentation.

