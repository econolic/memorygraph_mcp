#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

OIDC_HOST="${OIDC_HOST:-127.0.0.1}"
OIDC_PORT="${OIDC_PORT:-9010}"
MCP_HOST="${MCP_HOST:-127.0.0.1}"
MCP_PORT="${MCP_PORT:-8080}"
AUDIENCE="${AUDIENCE:-hybrid-kb-mcp}"
SUBJECT="${SUBJECT:-u1}"
WORKSPACE_ID="${WORKSPACE_ID:-w1}"
REQUIRED_SCOPES="${REQUIRED_SCOPES:-mcp.read}"
SHARED_SECRET="${SHARED_SECRET:-strict-oauth-smoke-secret-please-change-32chars}"
OIDC_READY_ATTEMPTS="${OIDC_READY_ATTEMPTS:-50}"
MCP_READY_ATTEMPTS="${MCP_READY_ATTEMPTS:-200}"
SMOKE_RETRY_SLEEP_S="${SMOKE_RETRY_SLEEP_S:-0.2}"

OIDC_ISSUER="http://${OIDC_HOST}:${OIDC_PORT}"
JWKS_URL="${OIDC_ISSUER}/.well-known/jwks.json"

cleanup() {
  if [[ -n "${MCP_PID:-}" ]] && kill -0 "${MCP_PID}" >/dev/null 2>&1; then
    kill "${MCP_PID}" >/dev/null 2>&1 || true
  fi
  if [[ -n "${OIDC_PID:-}" ]] && kill -0 "${OIDC_PID}" >/dev/null 2>&1; then
    kill "${OIDC_PID}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

PYTHONUNBUFFERED=1 python3 scripts/oidc_test_issuer.py serve \
  --host "${OIDC_HOST}" \
  --port "${OIDC_PORT}" \
  --issuer "${OIDC_ISSUER}" \
  --shared-secret "${SHARED_SECRET}" \
  >/tmp/oidc-smoke.log 2>&1 &
OIDC_PID=$!

OIDC_READY=0
for _ in $(seq 1 "${OIDC_READY_ATTEMPTS}"); do
  if curl -fsS "${OIDC_ISSUER}/healthz" >/dev/null 2>&1; then
    OIDC_READY=1
    break
  fi
  if ! kill -0 "${OIDC_PID}" >/dev/null 2>&1; then
    echo "OIDC test issuer exited before health check passed. See /tmp/oidc-smoke.log" >&2
    exit 1
  fi
  sleep "${SMOKE_RETRY_SLEEP_S}"
done

if [[ "${OIDC_READY}" != "1" ]]; then
  echo "OIDC test issuer did not become ready at ${OIDC_ISSUER}/healthz" >&2
  exit 1
fi

TOKEN="$(python3 scripts/oidc_test_issuer.py mint \
  --issuer "${OIDC_ISSUER}" \
  --audience "${AUDIENCE}" \
  --subject "${SUBJECT}" \
  --workspace-id "${WORKSPACE_ID}" \
  --scope "mcp.read mcp.write" \
  --roles "reader" \
  --shared-secret "${SHARED_SECRET}")"

export KB_HTTP_HOST="${MCP_HOST}"
export KB_HTTP_PORT="${MCP_PORT}"
export KB_AUTH_MODE="strict_oauth"
export KB_OAUTH_ISSUER_URL="${OIDC_ISSUER}"
export KB_OAUTH_AUDIENCE="${AUDIENCE}"
export KB_OAUTH_JWKS_URL="${JWKS_URL}"
export KB_OAUTH_REQUIRED_SCOPES="${REQUIRED_SCOPES}"
# Isolate smoke from any pre-exported stdio/self-hosted env in the shell.
export KB_VECTOR_BACKEND="memory"
export KB_GRAPH_BACKEND="memory"
export KB_METADATA_BACKEND="memory"
export KB_AUTO_INGEST_ENABLED="false"

PYTHONUNBUFFERED=1 PYTHONPATH=. python3 -m kb_mcp.server.transport_http >/tmp/mcp-smoke.log 2>&1 &
MCP_PID=$!

REQUEST_OK=0
for _ in $(seq 1 "${MCP_READY_ATTEMPTS}"); do
  if curl -fsS "http://${MCP_HOST}:${MCP_PORT}/mcp" \
    -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' \
    -H "Authorization: Bearer ${TOKEN}" \
    -d '{"jsonrpc":"2.0","id":"ready","method":"tools/list","params":{}}' \
    >/tmp/smoke-response.json 2>/dev/null; then
    REQUEST_OK=1
    break
  fi
  if ! kill -0 "${MCP_PID}" >/dev/null 2>&1; then
    echo "MCP server exited before smoke request succeeded. See /tmp/mcp-smoke.log" >&2
    exit 1
  fi
  sleep "${SMOKE_RETRY_SLEEP_S}"
done

if [[ "${REQUEST_OK}" != "1" ]]; then
  echo "Smoke request to http://${MCP_HOST}:${MCP_PORT}/mcp did not succeed after retries" >&2
  exit 1
fi

if [[ ! -s /tmp/smoke-response.json ]]; then
  echo "Smoke request returned empty response body (expected JSON-RPC response)" >&2
  exit 1
fi

echo "=== strict_oauth smoke result (tools/list) ==="
cat /tmp/smoke-response.json
echo
echo "issuer: ${OIDC_ISSUER}"
echo "jwks:   ${JWKS_URL}"
echo "mcp:    http://${MCP_HOST}:${MCP_PORT}/mcp"
