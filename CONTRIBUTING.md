# Contributing

## Scope and Expectations

This repository targets an **open-source self-hosted** Hybrid KB MCP server. Contributions should preserve:

- MCP tool/resource API compatibility
- server-side ACL enforcement
- self-hosted deployment safety defaults
- documentation accuracy

## Local Setup

```bash
.venv/bin/python -m pip install -e .[dev,rerank]
cp .env.example .env
```

For local-only development, keep `KB_HTTP_HOST=127.0.0.1`.

## Development Checks

Run before opening a PR:

```bash
make check-fast
```

Direct equivalent:

```bash
.venv/bin/ruff check .
.venv/bin/python -m mypy kb_mcp
.venv/bin/python -m pytest -q -m "not docker and not benchmark and not external"
```

## Docker E2E / Self-Hosted Smoke

Local quickstart stack:

```bash
docker compose up -d --build
```

Self-hosted release smoke (strict mode baseline):

```bash
cp .env.selfhosted.example .env
./scripts/release_selfhosted_smoke.sh
```

Minimal JSON-RPC smoke against a running HTTP MCP endpoint:

```bash
python3 scripts/jsonrpc_smoke.py --token "$TOKEN"
```

## PR Guidelines

- Keep changes scoped and explain tradeoffs in PR description.
- Add or update tests for behavioral changes.
- Mark slow or external checks with `docker`, `benchmark`, or `external` pytest markers.
- Update docs when runtime/config/user behavior changes.
- Call out security impact (auth/ACL/transport/storage) explicitly.
- Mention benchmark impact for retrieval changes (quality/latency/fusion/rerank/entity resolution).

## Commit Messages

No strict convention is required, but use clear, scoped messages.

Examples:

- `fix(auth): reject weak jwt secret in strict http mode`
- `docs(readme): clarify self-hosted support scope`
- `ci: add lint/type/test workflow`

