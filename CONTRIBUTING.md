# Contributing

## Scope and Expectations

This repository targets an **open-source self-hosted** Hybrid KB MCP server. Contributions should preserve:

- MCP tool/resource API compatibility
- server-side ACL enforcement
- self-hosted deployment safety defaults
- documentation accuracy

## Local Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev,rerank]
cp .env.example .env
```

For local-only development, keep `KB_HTTP_HOST=127.0.0.1`.

## Development Checks

Run before opening a PR:

```bash
ruff check .
mypy kb_mcp
pytest -s
```

If your environment needs explicit import path for ad-hoc tests:

```bash
PYTHONPATH=. pytest -s tests/test_router.py
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

## PR Guidelines

- Keep changes scoped and explain tradeoffs in PR description.
- Add or update tests for behavioral changes.
- Update docs when runtime/config/user behavior changes.
- Call out security impact (auth/ACL/transport/storage) explicitly.
- Mention benchmark impact for retrieval changes (quality/latency/fusion/rerank/entity resolution).

## Commit Messages

No strict convention is required, but use clear, scoped messages.

Examples:

- `fix(auth): reject weak jwt secret in strict http mode`
- `docs(readme): clarify self-hosted support scope`
- `ci: add lint/type/test workflow`

