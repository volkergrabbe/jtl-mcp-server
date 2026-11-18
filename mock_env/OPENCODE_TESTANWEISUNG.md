# Testanweisung: MCP-Connector gegen die Prism-Demo prüfen

**An:** opencode-Instanz (Erbauer des MCP-Connectors)
**Ziel:** Nachweisen, dass der Connector Authentifizierung, Session-Handling,
`tools/list` und die JTL-Fach-Tools gegen die lokale Mock-Umgebung korrekt
bedient.
**Umgebung:** ausschließlich **pve3** (`192.168.178.5`), Projekt
`/opt/jtl-mcp-demo`. **hpgen4 ist tabu.**

---

## 0. Regeln

1. Nur Testdaten. Es gibt keine echte JTL-Wawi.
2. Der MCP-Server ist strikt read-only. Es existieren keine schreibenden
   Tools; rufe keine schreibenden Endpunkte auf.
3. **Prism ignoriert Query-Parameter.** Jeder Aufruf eines Endpunkts liefert
   denselben statischen Beispieldatensatz. Filterverhalten (z. B.
   `sales_order_number=unbekannt` → 0 Treffer) darf **nicht** getestet
   werden. Prüfe Feldwerte, nicht Filterlogik.
4. Token und URLs sind Demo-Werte. Nicht in Produktivsysteme übernehmen.

---

## 1. Demo-Umgebung starten

Auf pve3:

```bash
ssh root@192.168.178.5
cd /opt/jtl-mcp-demo
./mock_env/start_demo.sh
```

Läuft der Connector auf einem **anderen Host**, MCP an alle Interfaces binden:

```bash
MCP_HOST=0.0.0.0 ./mock_env/start_demo.sh
```

Der Start blockiert und gibt Verbindungsdaten, `curl`-Beispiele und den
LiteLLM-Block aus. Beenden mit `Ctrl+C`; der Trap räumt Prism und den
MCP-Server auf.

Logs:

- `mock_env/prism.log`
- `mock_env/mcp-server.log`

---

## 2. Verbindungsdaten

| Parameter | Wert |
|---|---|
| MCP-URL (auf pve3) | `http://127.0.0.1:8099/mcp` |
| MCP-URL (LAN) | `http://192.168.178.5:8099/mcp` |
| MCP-Bearer-Token | `demo-secret-token-123` |
| JTL-Mock (nur serverintern) | `http://127.0.0.1:5883/api/eazybusiness/v1` |
| JTL-Bearer (base64) | `MDAwMDAwMDAtMDAwMC0wMDAwLTAwMDAtMDAwMDAwMDAwMDAx` |
| Protocol-Version | `2025-06-18` |

Pflicht-Header für MCP-Requests:

```text
Authorization: Bearer demo-secret-token-123
Content-Type: application/json
Accept: application/json, text/event-stream
```

Ab dem zweiten Request zusätzlich:

```text
mcp-session-id: <SID aus der initialize-Antwort>
MCP-Protocol-Version: 2025-06-18
```

---

## 3. Smoke-Tests mit curl

### 3.1 Ohne Token → 401

```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST \
  "http://127.0.0.1:8099/mcp" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"opencode","version":"1.0"}}}'
# Soll: 401
```

### 3.2 Falsches Token → 401

Gleicher Aufruf mit `-H "Authorization: Bearer falsches-token"`.
Soll: `401`, Body `{"error":"unauthorized",...}`.

### 3.3 initialize → Session-ID

```bash
curl -sS -D /tmp/mcp-headers.txt -o /tmp/mcp-init.json -X POST \
  "http://127.0.0.1:8099/mcp" \
  -H "Authorization: Bearer demo-secret-token-123" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"opencode","version":"1.0"}}}'

grep -i '^mcp-session-id:' /tmp/mcp-headers.txt
SID="$(grep -i '^mcp-session-id:' /tmp/mcp-headers.txt | tr -d '\r' | awk '{print $2}')"
```

Soll: HTTP `200`, `mcp-session-id` vorhanden, `result.serverInfo.name` =
`jtl-wawi`.

### 3.4 tools/list

```bash
curl -sS -X POST "http://127.0.0.1:8099/mcp" \
  -H "Authorization: Bearer demo-secret-token-123" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "mcp-session-id: $SID" \
  -H "MCP-Protocol-Version: 2025-06-18" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
```

Soll: 15 Tools. Verbindliche Namen:

```text
jtl_wawi_status
jtl_list_customers
jtl_get_customer
jtl_list_items
jtl_get_item
jtl_list_warehouses
jtl_get_item_stock
jtl_list_sales_orders
jtl_get_sales_order
jtl_list_sales_order_line_items
jtl_list_shipments
get_order_status
search_customer_orders
check_article_stock
get_shipment_tracking
```

### 3.5 Einen Fach-Tool aufrufen

```bash
curl -sS -X POST "http://127.0.0.1:8099/mcp" \
  -H "Authorization: Bearer demo-secret-token-123" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "mcp-session-id: $SID" \
  -H "MCP-Protocol-Version: 2025-06-18" \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"jtl_list_sales_orders","arguments":{"sales_order_number":"AU-2026-8841"}}}'
```

Soll: `result.isError` = `false`, `result.structuredContent` enthält die
Sollwerte aus Abschnitt 4.

---

## 4. Testmatrix mit Sollwerten

Die Support-Werkzeuge `get_order_status`, `search_customer_orders`,
`check_article_stock` und `get_shipment_tracking` existieren im Server und
liefern die Antworten fertig aufbereitet. Alternativ koennen die einzelnen
Fachdaten-Tools der folgenden Matrix genutzt werden.

| Fachaufgabe | Tool | Argumente | Sollwerte |
|---|---|---|---|
| Status | `jtl_wawi_status` | `{}` | `reachable=true`, `api_version="1"`, `feature_count=4` |
| Auftrag | `jtl_list_sales_orders` | `{"sales_order_number":"AU-2026-8841"}` | `count=1`, `number="AU-2026-8841"`, `customer_id=10420`, `payment_status="bezahlt"`, `delivery_status="versendet"`, `total_gross=1489.5`, `currency="EUR"`, `is_cancelled=false` |
| Kunde | `jtl_list_customers` | `{"search":"Musterbau"}` | `count=1`, `number="KD-10420"`, `company="Musterbau GmbH"`, `email="einkauf@musterbau-gmbh.de"`, `city="Bückeburg"` |
| Artikel | `jtl_list_items` | `{"search":"ART-5001"}` | `count=1`, `sku="ART-5001"`, `name="Industrie-Steuerungsmodul Pro X2"`, `price_net=249.0`, `is_active=true` |
| Bestand | `jtl_get_item_stock` | `{"item_id":5001}` | `count=1`, `quantity_total=142.0`, `quantity_locked_for_shipment=100.0`, `quantity_available=42.0`, `warehouse_name="Hauptlager Bückeburg"` |
| Versand | `jtl_list_shipments` | `{"sales_order_number":"AU-2026-8841"}` | `count=1`, `delivery_note_number="LS-2026-9912"`, `tracking_id="00340434161094012345"`, `delivery_date="2026-11-12T07:30:00+01:00"` |

Szenario-Werkzeuge (empfohlen fuer die Abnahme):

| Fachaufgabe | Tool | Argumente | Sollwerte |
|---|---|---|---|
| Auftragsstatus | `get_order_status` | `{"sales_order_number":"AU-2026-8841"}` | `order_number="AU-2026-8841"`, `customer_number="KD-10420"`, `customer_company="Musterbau GmbH"`, `payment_status="bezahlt"`, `delivery_status="versendet"`, `is_paid=true`, `total_gross=1489.5`, `currency="EUR"`, `tracking_id="00340434161094012345"` |
| Kundenorders | `search_customer_orders` | `{"customer_number":"KD-10420"}` | `customer_number="KD-10420"`, `customer_company="Musterbau GmbH"`, `customer_email="einkauf@musterbau-gmbh.de"`, `customer_city="Bückeburg"`, `order_count=1` |
| Artikelbestand | `check_article_stock` | `{"sku":"ART-5001"}` | `sku="ART-5001"`, `name="Industrie-Steuerungsmodul Pro X2"`, `price_net=249.0`, `available_quantity=42.0`, `incoming_quantity=100.0` |
| Sendungsverfolgung | `get_shipment_tracking` | `{"sales_order_number":"AU-2026-8841"}` | `delivery_note_number="LS-2026-9912"`, `carrier="DHL Paket"`, `tracking_id="00340434161094012345"`, `package_count=1` |

Zusätzlich prüfen:

| Fall | Erwartung |
|---|---|
| `initialize` ohne Token | HTTP 401 |
| `initialize` mit falschem Token | HTTP 401 |
| `tools/call` mit unbekanntem Tool-Namen | JSON-RPC-Fehler bzw. `isError=true` |
| Request ohne `mcp-session-id` nach initialize | HTTP 400 (Session nicht gefunden) |
| Request ohne `Accept`-Header | HTTP 406/415 |
| Ausgabe enthält keine internen JTL-Metafelder | nur die in der Matrix genannten Felder |

---

## 5. Nachweis des base64-Bearer-Tokens (outbound)

Der MCP-Server sendet an Prism:

```http
Authorization: Bearer MDAwMDAwMDAtMDAwMC0wMDAwLTAwMDAtMDAwMDAwMDAwMDAx
```

Prism akzeptiert **jedes** Bearer-Token. Ein HTTP 200 beweist daher nicht,
dass der Client den korrekten base64-Wert sendet. Der belastbare Nachweis
läuft über den Recording-Proxy im E2E-Test:

```bash
cd /opt/jtl-mcp-demo
.venv/bin/python -m pytest tests/test_e2e_prism.py -q -s
```

Der Test asserted:

```python
set(proxy_authorizations) == {"Bearer " + base64(api_key)}
```

Ergebnis: **4 passed**.

Wenn der Connector einen **eigenen** JTL-Client implementiert, muss dieser
exakt senden:

```text
Authorization: Bearer <base64(api_key)>
```

`Bearer` mit großem B; `bearer` wird von Prism abgelehnt.

---

## 6. Gesamte Suite

```bash
cd /opt/jtl-mcp-demo
python3 mock_env/seed_openapi.py          # Demo-Spec neu erzeugen
.venv/bin/python -m pytest -q             # 38 passed (34 Unit + 4 E2E)
.venv/bin/python -m ruff check .          # All checks passed
```

Der E2E-Test startet Prism, den Recording-Proxy und den MCP-Server selbst auf
dynamischen Ports. Ein bereits laufender Demo-Stack stört nicht.

---

## 7. Aufräumen

```bash
fuser -k 5883/tcp 8099/tcp
```

Oder `Ctrl+C` im Terminal von `start_demo.sh`.

**Kein** `pkill -f "prism"` über SSH: Die eigene SSH-Kommandozeile enthält das
Suchmuster und die Session wird mitgetötet.

---

## 8. Fehlerbilder

| Symptom | Ursache / Lösung |
|---|---|
| `401 Invalid security scheme used` | Demo-Spec hat kein `http`/`bearer`-Schema. `seed_openapi.py` erneut ausführen. |
| `404 NO_PATH_MATCHED_ERROR` | Basispfad fehlt in den Pfaden. Demo-Spec neu erzeugen; Prism ignoriert `servers.url`. |
| `401` trotz Token, Meldung `x-tenant-id` | Pflicht-Header in der Demo-Spec. `seed_openapi.py` setzt `required=false`. |
| `400 Session not found` | `mcp-session-id` fehlt oder ist abgelaufen. Neu `initialize` aufrufen. |
| `406 Not Acceptable` | `Accept: application/json, text/event-stream` fehlt. |
| `Connection refused` auf 8099 | MCP-Server nicht gestartet oder an `127.0.0.1` gebunden, Connector läuft remote. `MCP_HOST=0.0.0.0` setzen. |
| `Connection refused` auf 5883 | Prism nicht gestartet. `mock_env/prism.log` prüfen. |
| Leere/`string`-Antworten | Demo-Spec ohne `examples`. `seed_openapi.py` ausführen. |

---

## 9. Abnahmekriterien

- [ ] `initialize` mit Token liefert HTTP 200 und `mcp-session-id`.
- [ ] `initialize` ohne/mit falschem Token liefert HTTP 401.
- [ ] `tools/list` liefert exakt die 15 genannten Tools.
- [ ] Alle sechs Aufrufe aus Abschnitt 4 liefern die Sollwerte.
- [ ] `pytest tests/test_e2e_prism.py` → 4 passed.
- [ ] `pytest -q` → 38 passed.
- [ ] Keine schreibenden Aufrufe, keine echten JTL-/Produktivdaten.
