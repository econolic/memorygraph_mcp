#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.selfhosted.yml}"
ENV_FILE="${ENV_FILE:-.env}"
MCP_URL="${MCP_URL:-http://127.0.0.1:8080/mcp}"
WORKSPACE_ID="${WORKSPACE_ID:-w1}"
SUBJECT_ID="${SUBJECT_ID:-u1}"
SESSION_ID="${SESSION_ID:-release-smoke}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}. Copy .env.selfhosted.example to .env and fill secrets first." >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required" >&2
  exit 1
fi
if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required" >&2
  exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required" >&2
  exit 1
fi

mkdir -p .docker-data/qdrant .docker-data/neo4j/data .docker-data/mcp .docker-data/postgres

set -a
source "${ENV_FILE}"
set +a

export KB_AUTH_MODE="${KB_AUTH_MODE:-strict}"
if [[ "${KB_AUTH_MODE}" != "strict" ]]; then
  echo "This smoke script expects KB_AUTH_MODE=strict in ${ENV_FILE}. Current: ${KB_AUTH_MODE}" >&2
  exit 1
fi

if [[ -z "${KB_JWT_SECRET:-}" || "${KB_JWT_SECRET}" == "change-me" || "${KB_JWT_SECRET}" == "replace-with-strong-32plus-char-secret" || "${KB_JWT_SECRET}" == "replace-with-generated-strong-32plus-char-secret" ]]; then
  echo "KB_JWT_SECRET is missing or placeholder. Set a strong secret in ${ENV_FILE}." >&2
  exit 1
fi

jsonrpc() {
  local request_json="$1"
  local token="${2:-}"
  if [[ -n "${token}" ]]; then
    curl -sS "${MCP_URL}" \
      -H 'Content-Type: application/json' \
      -H 'Accept: application/json, text/event-stream' \
      -H "Authorization: Bearer ${token}" \
      -d "${request_json}"
  else
    curl -sS "${MCP_URL}" \
      -H 'Content-Type: application/json' \
      -H 'Accept: application/json, text/event-stream' \
      -d "${request_json}"
  fi
}

make_token() {
  local sub="$1"
  local workspace="$2"
  python3 - <<'PY' "${sub}" "${workspace}"
import os
import sys
try:
    import jwt
except Exception as exc:  # pragma: no cover
    raise SystemExit(f"PyJWT is required for smoke script: {exc}")

sub = sys.argv[1]
workspace = sys.argv[2]
secret = os.environ["KB_JWT_SECRET"]
print(jwt.encode({"sub": sub, "workspace_id": workspace, "roles": ["reader"]}, secret, algorithm="HS256"))
PY
}

wait_for_mcp() {
  local token="$1"
  local attempt
  for attempt in $(seq 1 60); do
    local response
    response="$(jsonrpc '{"jsonrpc":"2.0","id":"tools","method":"tools/list","params":{}}' "${token}" || true)"
    if python3 - <<'PY' "${response}"
import json, sys
raw = sys.argv[1]
try:
    data = json.loads(raw)
except Exception:
    raise SystemExit(1)
if "result" in data:
    raise SystemExit(0)
raise SystemExit(1)
PY
    then
      return 0
    fi
    sleep 2
  done
  echo "MCP endpoint did not become ready in time: ${MCP_URL}" >&2
  return 1
}

TOKEN="$(make_token "${SUBJECT_ID}" "${WORKSPACE_ID}")"
FOREIGN_TOKEN="$(make_token "u_forbidden" "w_forbidden")"

echo "[1/10] Starting self-hosted stack (${COMPOSE_FILE})"
docker compose -f "${COMPOSE_FILE}" up -d --build

echo "[2/10] Waiting for MCP endpoint"
wait_for_mcp "${TOKEN}"

echo "[3/10] Verifying tools/list and kb.route availability"
TOOLS_JSON="$(jsonrpc '{"jsonrpc":"2.0","id":"tools","method":"tools/list","params":{}}' "${TOKEN}")"
python3 - <<'PY' "${TOOLS_JSON}"
import json, sys
data = json.loads(sys.argv[1])
tools = {t["name"] for t in data["result"]["tools"]}
required = {"kb.route", "kb.search", "kb.memory.upsert", "kb.memory.search", "kb.memory.delete", "kb.ingest.filesystem"}
missing = sorted(required - tools)
if missing:
    raise SystemExit(f"Missing tools: {missing}")
print("tools ok")
PY

echo "[4/10] Ingesting repo source path (/app/kb_mcp)"
INGEST_JSON="$(jsonrpc "$(cat <<JSON
{"jsonrpc":"2.0","id":"ingest","method":"tools/call","params":{"name":"kb.ingest.filesystem","arguments":{"root_path":"/app/kb_mcp","workspace_id":"${WORKSPACE_ID}","acl_subject":"${SUBJECT_ID}"}}}
JSON
)" "${TOKEN}")"
python3 - <<'PY' "${INGEST_JSON}"
import json, sys
data = json.loads(sys.argv[1])
if "error" in data:
    raise SystemExit(data["error"])
result = data["result"]
if result.get("isError") is True:
    raise SystemExit(result)
print("ingest ok")
PY

echo "[5/10] Search with citations"
SEARCH_JSON="$(jsonrpc "$(cat <<JSON
{"jsonrpc":"2.0","id":"search","method":"tools/call","params":{"name":"kb.search","arguments":{"payload":{"query":"Hybrid Retrieval MCP server", "mode":"hybrid","top_k":5,"workspace_id":"${WORKSPACE_ID}","session_id":"${SESSION_ID}","include_memory":false,"filters":{"acl":{"subject":"${SUBJECT_ID}","workspace_id":"${WORKSPACE_ID}","roles":[]}},"graph":{"expand_depth":1,"edge_types":[],"max_nodes":50},"rerank":{"enabled":false,"provider":"cross_encoder","top_n":5}}}}}
JSON
)" "${TOKEN}")"
TOP_URI="$(python3 - <<'PY' "${SEARCH_JSON}"
import json, sys
data = json.loads(sys.argv[1])
res = data["result"]
if res.get("isError") is True:
    raise SystemExit(res)
payload = res.get("structuredContent")
if not isinstance(payload, dict):
    content = res.get("content", [])
    if content and isinstance(content[0], dict):
        if isinstance(content[0].get("json"), dict):
            payload = content[0]["json"]
        elif isinstance(content[0].get("text"), str):
            payload = json.loads(content[0]["text"])
if not isinstance(payload, dict):
    raise SystemExit(f"Unsupported MCP tool response shape: {res}")
results = payload.get("results", [])
if not results:
    raise SystemExit("No search results")
print(results[0].get("uri", ""))
PY
)"
if [[ -z "${TOP_URI}" ]]; then
  echo "Search did not return a resource URI" >&2
  exit 1
fi
TOP_CITATION_JSON="$(python3 - <<'PY' "${SEARCH_JSON}"
import json, sys
data = json.loads(sys.argv[1])
res = data["result"]
payload = res.get("structuredContent")
if not isinstance(payload, dict):
    content = res.get("content", [])
    if content and isinstance(content[0], dict):
        if isinstance(content[0].get("json"), dict):
            payload = content[0]["json"]
        elif isinstance(content[0].get("text"), str):
            payload = json.loads(content[0]["text"])
if not isinstance(payload, dict):
    raise SystemExit(f"Unsupported MCP tool response shape: {res}")
results = payload.get("results", [])
if not results:
    raise SystemExit("No search results")
cits = results[0].get("citations", [])
if not cits or not isinstance(cits[0], dict):
    raise SystemExit("No citation object in search result")
print(json.dumps(cits[0], ensure_ascii=False))
PY
)"

echo "[6/10] Route wrapper flow (HTTP)"
python3 ./scripts/kb_route_wrapper.py --transport http --token "${TOKEN}" "Какие связи есть у kb.route в проекте?" >/dev/null

echo "[7/10] Memory lifecycle (upsert/search/delete)"
UPSERT_JSON="$(jsonrpc "$(cat <<JSON
{"jsonrpc":"2.0","id":"mem-upsert","method":"tools/call","params":{"name":"kb.memory.upsert","arguments":{"payload":{"workspace_id":"${WORKSPACE_ID}","subject":"${SUBJECT_ID}","session_id":"${SESSION_ID}","items":[{"type":"decision","text":"Release smoke confirms strict self-hosted baseline","confidence":0.95,"citations":[${TOP_CITATION_JSON}]}]}}}}
JSON
)" "${TOKEN}")"
MEMORY_ID="$(python3 - <<'PY' "${UPSERT_JSON}"
import json, sys
data = json.loads(sys.argv[1])
res = data["result"]
if res.get("isError") is True:
    raise SystemExit(res)
payload = res.get("structuredContent")
if not isinstance(payload, dict):
    content = res.get("content", [])
    if content and isinstance(content[0], dict):
        if isinstance(content[0].get("json"), dict):
            payload = content[0]["json"]
        elif isinstance(content[0].get("text"), str):
            payload = json.loads(content[0]["text"])
if not isinstance(payload, dict):
    raise SystemExit(f"Unsupported MCP tool response shape: {res}")
ids = payload.get("stored_ids", [])
if not ids:
    raise SystemExit("No stored_ids")
print(ids[0])
PY
)"
jsonrpc "$(cat <<JSON
{"jsonrpc":"2.0","id":"mem-search","method":"tools/call","params":{"name":"kb.memory.search","arguments":{"payload":{"query":"strict self-hosted baseline","workspace_id":"${WORKSPACE_ID}","subject":"${SUBJECT_ID}","session_id":"${SESSION_ID}","top_k":5}}}}
JSON
)" "${TOKEN}" >/dev/null
jsonrpc "$(cat <<JSON
{"jsonrpc":"2.0","id":"mem-delete","method":"tools/call","params":{"name":"kb.memory.delete","arguments":{"payload":{"workspace_id":"${WORKSPACE_ID}","subject":"${SUBJECT_ID}","ids":["${MEMORY_ID}"]}}}}
JSON
)" "${TOKEN}" >/dev/null

echo "[8/10] ACL denial for foreign workspace token (resource read)"
DENY_JSON="$(jsonrpc "$(cat <<JSON
{"jsonrpc":"2.0","id":"resource-deny","method":"resources/read","params":{"uri":"${TOP_URI}"}} 
JSON
)" "${FOREIGN_TOKEN}")"
python3 - <<'PY' "${DENY_JSON}"
import json, sys
data = json.loads(sys.argv[1])
payload = data.get("result", {})
if isinstance(payload, dict) and payload.get("contents"):
    for item in payload["contents"]:
        text = item.get("text", "")
        if "forbidden" in text:
            print("acl deny ok")
            raise SystemExit(0)
if "error" in data and "forbidden" in str(data["error"]).lower():
    print("acl deny ok")
    raise SystemExit(0)
raise SystemExit(f"Expected forbidden resource read, got: {data}")
PY

echo "[9/10] Persistence check across restart"
PERSIST_UPSERT_JSON="$(jsonrpc "$(cat <<JSON
{"jsonrpc":"2.0","id":"persist-upsert","method":"tools/call","params":{"name":"kb.memory.upsert","arguments":{"payload":{"workspace_id":"${WORKSPACE_ID}","subject":"${SUBJECT_ID}","session_id":"${SESSION_ID}","items":[{"type":"decision","text":"Persistence smoke marker","confidence":0.95,"citations":[${TOP_CITATION_JSON}]}]}}}}
JSON
)" "${TOKEN}")"
PERSIST_ID="$(python3 - <<'PY' "${PERSIST_UPSERT_JSON}"
import json, sys
data = json.loads(sys.argv[1])
res = data["result"]
if res.get("isError") is True:
    raise SystemExit(res)
payload = res.get("structuredContent")
if not isinstance(payload, dict):
    content = res.get("content", [])
    if content and isinstance(content[0], dict):
        if isinstance(content[0].get("json"), dict):
            payload = content[0]["json"]
        elif isinstance(content[0].get("text"), str):
            payload = json.loads(content[0]["text"])
if not isinstance(payload, dict):
    raise SystemExit(f"Unsupported MCP tool response shape: {res}")
print(payload["stored_ids"][0])
PY
)"
docker compose -f "${COMPOSE_FILE}" restart mcp >/dev/null
wait_for_mcp "${TOKEN}"
PERSIST_SEARCH_JSON="$(jsonrpc "$(cat <<JSON
{"jsonrpc":"2.0","id":"persist-search","method":"tools/call","params":{"name":"kb.memory.search","arguments":{"payload":{"query":"Persistence smoke marker","workspace_id":"${WORKSPACE_ID}","subject":"${SUBJECT_ID}","session_id":"${SESSION_ID}","top_k":5}}}}
JSON
)" "${TOKEN}")"
python3 - <<'PY' "${PERSIST_SEARCH_JSON}" "${PERSIST_ID}"
import json, sys
data = json.loads(sys.argv[1])
expected = sys.argv[2]
res = data["result"]
if res.get("isError") is True:
    raise SystemExit(res)
payload = res.get("structuredContent")
if not isinstance(payload, dict):
    content = res.get("content", [])
    if content and isinstance(content[0], dict):
        if isinstance(content[0].get("json"), dict):
            payload = content[0]["json"]
        elif isinstance(content[0].get("text"), str):
            payload = json.loads(content[0]["text"])
if not isinstance(payload, dict):
    raise SystemExit(f"Unsupported MCP tool response shape: {res}")
hits = payload.get("results", [])
matched = False
for h in hits:
    if h.get("id") == expected:
        matched = True
        break
    uri = h.get("uri")
    if isinstance(uri, str) and uri.endswith(f"/{expected}"):
        matched = True
        break
if not matched:
    raise SystemExit(f"Persisted memory id not found after restart: {expected}")
print("persistence ok")
PY
jsonrpc "$(cat <<JSON
{"jsonrpc":"2.0","id":"persist-delete","method":"tools/call","params":{"name":"kb.memory.delete","arguments":{"payload":{"workspace_id":"${WORKSPACE_ID}","subject":"${SUBJECT_ID}","ids":["${PERSIST_ID}"]}}}}
JSON
)" "${TOKEN}" >/dev/null

echo "[10/10] Complete"
echo "Self-hosted smoke completed successfully."
echo "Optional manual check: stop Neo4j and verify kb.search fallback_mode=vector on relation-impact query."
