#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Healthcheck fuer den JTL-Wawi MCP-Server.
#
# Prueft zwei Dinge:
#   1. Ohne Token muss der Server 401 liefern (Auth ist aktiv).
#   2. Mit Token muss eine MCP-initialize-Anfrage erfolgreich beantwortet werden.
#
# Aufruf:
#   MCP_SERVER_AUTH_TOKEN=... ./deploy/healthcheck.sh [http://127.0.0.1:8080/mcp]
#
# Exit-Codes: 0 = ok, 1 = fehlgeschlagen
# ---------------------------------------------------------------------------
set -euo pipefail

URL="${1:-http://127.0.0.1:8080/mcp}"
TOKEN="${MCP_SERVER_AUTH_TOKEN:-}"
TIMEOUT="${HEALTHCHECK_TIMEOUT:-10}"

if [[ -z "${TOKEN}" ]]; then
    printf 'FEHLER: MCP_SERVER_AUTH_TOKEN ist nicht gesetzt.\n' >&2
    exit 1
fi

command -v curl >/dev/null 2>&1 || { printf 'FEHLER: curl fehlt.\n' >&2; exit 1; }

INIT_BODY='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"healthcheck","version":"1.0"}}}'

printf 'Pruefe %s ...\n' "${URL}"

unauth_code="$(curl -sS -m "${TIMEOUT}" -o /dev/null -w '%{http_code}' \
    -X POST "${URL}" \
    -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' \
    -d "${INIT_BODY}" || echo 000)"

if [[ "${unauth_code}" != "401" ]]; then
    printf 'FEHLER: Ohne Token wurde HTTP %s erwartet (401).\n' "${unauth_code}" >&2
    exit 1
fi
printf '  [ok] Authentifizierung aktiv (401 ohne Token)\n'

auth_code="$(curl -sS -m "${TIMEOUT}" -o /tmp/jtl-mcp-healthcheck.out -w '%{http_code}' \
    -X POST "${URL}" \
    -H "Authorization: Bearer ${TOKEN}" \
    -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' \
    -d "${INIT_BODY}" || echo 000)"

if [[ "${auth_code}" != "200" ]]; then
    printf 'FEHLER: Mit Token wurde HTTP %s erwartet (200).\n' "${auth_code}" >&2
    rm -f /tmp/jtl-mcp-healthcheck.out
    exit 1
fi

if ! grep -q '"result"' /tmp/jtl-mcp-healthcheck.out 2>/dev/null; then
    printf 'FEHLER: Antwort enthaelt kein JSON-RPC-Ergebnis.\n' >&2
    head -c 400 /tmp/jtl-mcp-healthcheck.out >&2 || true
    rm -f /tmp/jtl-mcp-healthcheck.out
    exit 1
fi
rm -f /tmp/jtl-mcp-healthcheck.out

printf '  [ok] MCP-initialize erfolgreich (HTTP 200)\n'
printf 'Alles in Ordnung.\n'
