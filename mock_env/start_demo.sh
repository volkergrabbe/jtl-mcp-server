#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# JTL-MCP Demo- und Testumgebung ohne JTL-Wawi
#
# Startet:
#   1. Stoplight Prism als Mock der JTL-OpenAPI-Spec (Port 5883)
#   2. den FastMCP-Server gegen diesen Mock (Port 8099)
#
# Beenden mit Ctrl+C. Alle Prozesse werden über den EXIT-Trap aufgeräumt.
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

PRISM_HOST="${PRISM_HOST:-127.0.0.1}"
PRISM_PORT="${PRISM_PORT:-5883}"
MCP_HOST="${MCP_HOST:-127.0.0.1}"
MCP_PORT="${MCP_PORT:-8099}"
JTL_API_KEY="00000000-0000-0000-0000-000000000001"
MCP_SERVER_AUTH_TOKEN="demo-secret-token-123"
JTL_API_PATH="/api/eazybusiness/v1"
PRISM_SPEC="${PROJECT_ROOT}/mock_env/jtl_erp_demo.json"
PRISM_LOG="${PROJECT_ROOT}/mock_env/prism.log"
MCP_LOG="${PROJECT_ROOT}/mock_env/mcp-server.log"

PYTHON="${PROJECT_ROOT}/.venv/bin/python"
if [[ ! -x "${PYTHON}" ]]; then
  PYTHON="$(command -v python3)"
fi

PRISM_PID=""
MCP_PID=""

cleanup() {
  local exit_code=$?
  trap - EXIT INT TERM
  if [[ -n "${MCP_PID}" ]] && kill -0 "${MCP_PID}" 2>/dev/null; then
    kill "${MCP_PID}" 2>/dev/null || true
    wait "${MCP_PID}" 2>/dev/null || true
  fi
  if [[ -n "${PRISM_PID}" ]] && kill -0 "${PRISM_PID}" 2>/dev/null; then
    kill "${PRISM_PID}" 2>/dev/null || true
    wait "${PRISM_PID}" 2>/dev/null || true
  fi
  exit "${exit_code}"
}
trap cleanup EXIT INT TERM

# --- Voraussetzungen -------------------------------------------------------
# Node.js suchen: PATH, JTL_MCP_NODE_BIN oder portables Node in .tools/node.
find_node_bin() {
  local candidate
  for candidate in "${JTL_MCP_NODE_BIN:-}" \
      "${PROJECT_ROOT}/.tools/node/bin" \
      "${PROJECT_ROOT}/../.tools/node/bin"; do
    [[ -n "${candidate}" ]] || continue
    if [[ -x "${candidate}/npx" ]]; then
      printf '%s' "${candidate}"
      return 0
    fi
  done
  command -v npx >/dev/null 2>&1 || return 1
  dirname "$(command -v npx)"
}

if ! NODE_BIN="$(find_node_bin)"; then
  cat >&2 <<'EOF'
FEHLER: npx (Node.js) ist nicht installiert.

  Option 1: Node.js >= 18 installieren
  Option 2: portables Node.js bereitstellen (ohne Root-Rechte):
      curl -fsSL https://nodejs.org/dist/v22.22.1/node-v22.22.1-linux-x64.tar.xz \
        | tar -xJ -C .tools --strip-components=1
  Danach JTL_MCP_NODE_BIN="$PWD/.tools/node/bin" setzen.
EOF
  exit 1
fi
export PATH="${NODE_BIN}:${PATH}"
echo "Node.js: $(node --version) (${NODE_BIN})"

if [[ ! -f "${PRISM_SPEC}" || "${RESEED:-0}" == "1" ]]; then
  echo "Erzeuge Demo-Spec aus mock_env/jtl_erp_1.1.json ..."
  "${PYTHON}" mock_env/seed_openapi.py
fi

if [[ ! -x "${PROJECT_ROOT}/.venv/bin/python" ]]; then
  echo "Hinweis: .venv fehlt. Lege virtuelle Umgebung an und installiere Abhängigkeiten ..."
  python3 -m venv .venv
  .venv/bin/python -m pip install -q --upgrade pip
  .venv/bin/python -m pip install -q -e ".[dev]"
  PYTHON="${PROJECT_ROOT}/.venv/bin/python"
fi

# --- 1. Prism starten ------------------------------------------------------
echo "Starte Prism-Mock auf http://${PRISM_HOST}:${PRISM_PORT} ..."
npx --yes @stoplight/prism-cli mock \
  -h "${PRISM_HOST}" -p "${PRISM_PORT}" \
  "${PRISM_SPEC}" >"${PRISM_LOG}" 2>&1 &
PRISM_PID=$!

for _ in $(seq 1 120); do
  if curl -s -o /dev/null "http://${PRISM_HOST}:${PRISM_PORT}${JTL_API_PATH}/feature" \
      -H "Authorization: Bearer $(printf '%s' "${JTL_API_KEY}" | base64 -w0)"; then
    break
  fi
  if ! kill -0 "${PRISM_PID}" 2>/dev/null; then
    echo "FEHLER: Prism ist beendet. Log: ${PRISM_LOG}" >&2
    tail -n 40 "${PRISM_LOG}" >&2 || true
    exit 1
  fi
  sleep 0.5
done

if ! curl -s -o /dev/null "http://${PRISM_HOST}:${PRISM_PORT}${JTL_API_PATH}/feature" \
    -H "Authorization: Bearer $(printf '%s' "${JTL_API_KEY}" | base64 -w0)"; then
  echo "FEHLER: Prism wurde nicht erreichbar. Log: ${PRISM_LOG}" >&2
  tail -n 40 "${PRISM_LOG}" >&2 || true
  exit 1
fi
echo "Prism ist bereit."

# --- 2. MCP-Server starten -------------------------------------------------
echo "Starte JTL-MCP-Server auf http://${MCP_HOST}:${MCP_PORT}/mcp ..."
JTL_BASE_URL="http://${PRISM_HOST}:${PRISM_PORT}" \
JTL_API_PATH="${JTL_API_PATH}" \
JTL_API_KEY="${JTL_API_KEY}" \
MCP_SERVER_AUTH_TOKEN="${MCP_SERVER_AUTH_TOKEN}" \
MCP_HOST="${MCP_HOST}" \
MCP_PORT="${MCP_PORT}" \
MCP_PATH="/mcp" \
MCP_LOG_LEVEL="INFO" \
PYTHONPATH="${PROJECT_ROOT}/src" \
"${PYTHON}" -m jtl_mcp >"${MCP_LOG}" 2>&1 &
MCP_PID=$!

for _ in $(seq 1 60); do
  status="$(curl -s -o /dev/null -w '%{http_code}' -X POST \
    "http://${MCP_HOST}:${MCP_PORT}/mcp" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -d '{"jsonrpc":"2.0","id":0,"method":"ping","params":{}}' || true)"
  if [[ "${status}" == "401" || "${status}" == "200" ]]; then
    break
  fi
  if ! kill -0 "${MCP_PID}" 2>/dev/null; then
    echo "FEHLER: MCP-Server ist beendet. Log: ${MCP_LOG}" >&2
    tail -n 40 "${MCP_LOG}" >&2 || true
    exit 1
  fi
  sleep 0.5
done

BASE64_TOKEN="$(printf '%s' "${JTL_API_KEY}" | base64 -w0)"

cat <<EOF

================================================================================
  JTL-MCP Demo-Umgebung ist bereit
================================================================================

  Prism-Mock (JTL-API):  http://${PRISM_HOST}:${PRISM_PORT}${JTL_API_PATH}
  MCP-Server:            http://${MCP_HOST}:${MCP_PORT}/mcp
  MCP-Bearer-Token:      ${MCP_SERVER_AUTH_TOKEN}
  JTL-Bearer-Token:      ${BASE64_TOKEN}

  Logs:
    Prism:               ${PRISM_LOG}
    MCP-Server:          ${MCP_LOG}

  Beenden mit Ctrl+C.

--------------------------------------------------------------------------------
  curl-Test gegen den Prism-Mock (JTL-API)
--------------------------------------------------------------------------------
curl -sS \\
  -H "Authorization: Bearer ${BASE64_TOKEN}" \\
  "http://${PRISM_HOST}:${PRISM_PORT}${JTL_API_PATH}/salesOrders?pageNumber=1&pageSize=50"

curl -sS \\
  -H "Authorization: Bearer ${BASE64_TOKEN}" \\
  "http://${PRISM_HOST}:${PRISM_PORT}${JTL_API_PATH}/deliveryNotes?salesOrderNumber=AU-2026-8841"

--------------------------------------------------------------------------------
  curl-Test gegen den MCP-Server (Streamable HTTP, initialize)
--------------------------------------------------------------------------------
curl -sS -X POST "http://${MCP_HOST}:${MCP_PORT}/mcp" \\
  -H "Authorization: Bearer ${MCP_SERVER_AUTH_TOKEN}" \\
  -H "Content-Type: application/json" \\
  -H "Accept: application/json, text/event-stream" \\
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"demo","version":"1.0"}}}'

Hinweis: Ein vollständiger MCP-Tool-Aufruf braucht eine Session (initialize ->
Antwort-Header "mcp-session-id" -> tools/list mit diesem Header). Für den
kompletten Roundtrip den E2E-Test nutzen:
  .venv/bin/python -m pytest tests/test_e2e_prism.py -q -s

--------------------------------------------------------------------------------
  Werkzeuge des MCP-Servers (15, alle read-only)
--------------------------------------------------------------------------------
  Fachdaten:  jtl_wawi_status, jtl_list_customers, jtl_get_customer,
              jtl_list_items, jtl_get_item, jtl_list_warehouses,
              jtl_get_item_stock, jtl_list_sales_orders, jtl_get_sales_order,
              jtl_list_sales_order_line_items, jtl_list_shipments
  Support:    get_order_status, search_customer_orders,
              check_article_stock, get_shipment_tracking

--------------------------------------------------------------------------------
  LiteLLM-Konfigurationsblock (deploy/litellm_config.yaml)
--------------------------------------------------------------------------------
mcp_servers:
  jtl_wawi:
    url: "http://${MCP_HOST}:${MCP_PORT}/mcp"
    transport: "http"
    auth_type: "bearer_token"
    auth_value: "os.environ/JTL_MCP_AUTH_TOKEN"
    available_on_public_internet: false

  # In der Shell vor dem LiteLLM-Start setzen:
  #   export JTL_MCP_AUTH_TOKEN="${MCP_SERVER_AUTH_TOKEN}"
  # Clients erreichen das Gateway danach unter http://<litellm-host>:4000/mcp

================================================================================
EOF

wait "${MCP_PID}"
