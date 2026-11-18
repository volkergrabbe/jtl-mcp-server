# JTL-Wawi Read-Only MCP Server

Produktionsreifer, strikt lesender **Model Context Protocol (MCP) Server** für
JTL-Wawi. Der Server läuft als isolierter Dienst in einem **Proxmox-LXC** und
wird über **LiteLLM** an ein lokales LLM angebunden.

Zielgruppe: Innendienst und Kundensupport eines B2B/E-Commerce-Kunden, die
revisionssichere Echtzeitauskunft zu Aufträgen, Kunden, Artikeln,
Lagerbeständen und Versandstatus benötigen.

---

## 1. Sicherheitskonzept

| Schutz | Umsetzung |
|---|---|
| **Strikt read-only** | Der HTTP-Client besitzt ausschließlich `GET`-Operationen. Ein interner Wächter wirft `JtlReadOnlyViolation`, sobald eine andere Methode versucht wird. Es existiert kein schreibendes Werkzeug. |
| **Payload-Komprimierung** | Jede API-Antwort wird auf ein flaches JSON mit **max. 6–10 Feldern** je Datensatz reduziert (durchgesetzt per Pydantic-Modellen, geprüft im Test `test_every_output_model_stays_within_field_budget`). Interne Metafelder der JTL-API gelangen nicht in den LLM-Kontext. |
| **Authentifizierung** | Der MCP-Server prüft jedes HTTP-Request gegen das statische Bearer-Token `MCP_SERVER_AUTH_TOKEN` (timing-sicherer Vergleich). Zusätzlich authentifiziert sich der Server gegenüber JTL-Wawi mit dem API-Key der Wawi. |
| **Systemhärtung** | systemd-Unit mit `ProtectSystem=strict`, `NoNewPrivileges`, leerer Capability-Liste, `SystemCallFilter=@system-service`, eigenem unprivilegiertem System-Benutzer. |
| **Netz** | Port 8080 nur im internen Netz freigeben; im LiteLLM-Gateway `available_on_public_internet: false`. |

---

## 2. Architektur

```text
LiteLLM / Client
      │  HTTP  POST /mcp  (Authorization: Bearer <MCP_SERVER_AUTH_TOKEN>)
      ▼
┌──────────────────────────────────────────────┐
│  JTL-Wawi MCP Server (FastMCP, Port 8080)    │
│  BearerAuthMiddleware → Tool → Payload-Filter│
└──────────────────────────────────────────────┘
      │  HTTP  GET  (Authorization: Bearer <base64-api-key>)
      ▼
JTL-Wawi API (JTL.Wawi.Rest.exe, Port 5883)  →  MSSQL (JTL-Wawi)
```

### Verzeichnisstruktur

```text
jtl-mcp-server/
├── pyproject.toml           # Abhängigkeiten, Entry-Point, pytest/ruff-Konfiguration
├── .env.example             # Vorlage für Umgebungsvariablen
├── .gitignore
├── README.md
├── src/
│   └── jtl_mcp/
│       ├── __init__.py
│       ├── __main__.py      # python -m jtl_mcp
│       ├── config.py        # Pydantic Settings (URL, API-Key, AppId, Timeouts, Auth-Token)
│       ├── jtl_client.py    # Async httpx-Client mit Retry, Timeout, Fehler-Mapping
│       ├── models.py        # Kompakte Output-Schemas (Token-optimiert)
│       └── server.py        # FastMCP, Bearer-Auth-Middleware, Tool-Definitionen
├── mock_env/
│   ├── jtl_erp_1.1.json     # Offizielle JTL-ERP-OpenAPI-Spec
│   ├── seed_openapi.py      # Erzeugt die Demo-Spec mit deutschen B2B-Beispieldaten
│   ├── jtl_erp_demo.json    # Aufbereitete Spec für Stoplight Prism
│   └── start_demo.sh        # Startet Prism + MCP-Server für die Live-Demo
├── tests/
│   ├── conftest.py          # Fixtures (Settings, respx-Router)
│   ├── mock_data.py         # Realistische JTL-Wawi-Payloads
│   ├── test_tools.py        # Unit-Tests (27 Tests)
│   └── test_e2e_prism.py    # E2E-Integrationstest gegen Prism (3 Tests)
└── deploy/
    ├── install.sh           # Installation als systemd-Dienst
    ├── uninstall.sh         # Deinstallation
    ├── jtl-mcp-server.service
    ├── healthcheck.sh       # Healthcheck für Monitoring
    ├── litellm_config.yaml.example
    └── PROXMOX_LXC.md       # Anleitung für den LXC-Betrieb
```

---

## 3. Voraussetzungen

* Python **3.11+** (entwickelt und getestet mit 3.14)
* JTL-Wawi **1.9 / 1.10** (oder neuer) inkl. laufender **JTL-Wawi API**
  (`JTL.Wawi.Rest.exe`, Standardport 5883)
* Ein API-Key aus JTL-Wawi: `Admin → Benutzer / Rechte → Benutzer → Key erzeugen`
* LiteLLM-Proxy als MCP-Gateway (optional, für den LLM-Anschluss)
* Proxmox LXC (unprivileged) als Zielumgebung

---

## 4. Installation (Entwicklung)

```bash
cd jtl-mcp-server

python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"

cp .env.example .env
# .env bearbeiten: JTL_API_KEY, MCP_SERVER_AUTH_TOKEN, JTL_BASE_URL

.venv/bin/jtl-mcp-server          # bzw. python -m jtl_mcp
```

Der MCP-Endpunkt ist danach unter `http://<host>:8080/mcp` erreichbar.

---

## 5. Konfiguration

Alle Werte kommen aus Umgebungsvariablen bzw. der `.env`-Datei
(Siehe `.env.example`).

### JTL-Wawi API

| Variable | Default | Bedeutung |
|---|---|---|
| `JTL_BASE_URL` | `http://localhost:5883` | Basis-URL des JTL-Wawi-API-Servers |
| `JTL_API_PATH` | `/api/eazybusiness/v1` | Pfad-Präfix; `/rest/eazybusiness/v1` für den in Wawi integrierten REST-Server |
| `JTL_API_KEY` | – | **Pflicht.** API-Key aus JTL-Wawi |
| `JTL_API_KEY_B64` | `false` | `true`, falls der Key bereits base64-kodiert ist |
| `JTL_APP_ID` | – | Optionale App-Id (Dokumentation) |
| `JTL_APP_VERSION` | `1.0.0` | Version der registrierten App |
| `JTL_TIMEOUT` / `JTL_CONNECT_TIMEOUT` | `20` / `10` | Timeouts in Sekunden |
| `JTL_MAX_RETRIES` | `3` | Wiederholungen bei Timeout/429/5xx |
| `JTL_BACKOFF_SECONDS` | `0.5` | Basis-Wartezeit (exponentiell) |
| `JTL_VERIFY_TLS` | `true` | TLS-Prüfung (in Produktion aktiv) |
| `JTL_PAGE_SIZE` / `JTL_MAX_PAGE_SIZE` | `50` / `200` | Seitengrößen der Listenabfragen |

### MCP-Server

| Variable | Default | Bedeutung |
|---|---|---|
| `MCP_SERVER_AUTH_TOKEN` | – | **Pflicht.** Statisches Bearer-Token für eingehende Requests |
| `MCP_HOST` / `MCP_PORT` | `0.0.0.0` / `8080` | Bind-Adresse und Port |
| `MCP_PATH` | `/mcp` | Pfad des Streamable-HTTP-Endpunkts |
| `MCP_ALLOWED_HOSTS` | – | Komma-Liste; gesetzt ⇒ Host-Origin-Protection aktiv |
| `MCP_ALLOWED_ORIGINS` | – | Komma-Liste erlaubter Origins |
| `MCP_STATELESS_HTTP` | `false` | Stateless-Modus (empfohlen hinter Load-Balancern) |
| `MCP_LOG_LEVEL` | `INFO` | Log-Level |

> **Zum API-Key:** Die JTL-Wawi erwartet ein **base64-kodiertes** Bearer-Token.
> Ist `JTL_API_KEY` der rohe GUID-String, kodiert der Server ihn automatisch
> (Default). Bereits kodierte Werte werden mit `JTL_API_KEY_B64=true` unverändert
> weitergereicht.

---

## 6. Werkzeuge (Tools)

### 6.1 Fachdaten (je Entität)

| Tool | Parameter | Ergebnis |
|---|---|---|
| `jtl_wawi_status` | – | Erreichbarkeit, API-Version, Feature-Anzahl |
| `jtl_list_customers` | `search`, `customer_number`, `customer_group_id`, `limit` | Kundenliste (8 Felder) |
| `jtl_get_customer` | `customer_id` | Kundendetails inkl. Rechnungs-/Lieferanschrift (10 Felder) |
| `jtl_list_items` | `search`, `category_id`, `limit` | Artikel inkl. Preisen, EAN (10 Felder) |
| `jtl_get_item` | `item_id` | Artikeldetails inkl. EK-Preis, Gewichte (10 Felder) |
| `jtl_list_warehouses` | – | Lager inkl. Code und Typ (6 Felder) |
| `jtl_get_item_stock` | `item_id` | Bestand je Lager inkl. verfügbarer Menge (9 Felder) |
| `jtl_list_sales_orders` | `sales_order_number`, `external_order_number`, `customer_id`, `created_since`, `created_until`, `is_cancelled`, `limit` | Auftragsliste mit Status (10 Felder) |
| `jtl_get_sales_order` | `sales_order_id` | Auftragsdetails inkl. Anschriften (10 Felder) |
| `jtl_list_sales_order_line_items` | `sales_order_id` | Positionen des Auftrags (10 Felder) |
| `jtl_list_shipments` | `sales_order_number`, `customer_id`, `limit` | Versandstatus je Paket mit Tracking (9 Felder) |

### 6.2 Support-Szenarien (vorkompilierte Fachfragen)

Diese Werkzeuge beantworten die typischen Support-Fragen in einem Durchgang
und liefern das Ergebnis fertig aufbereitet:

| Tool | Parameter | Ergebnis |
|---|---|---|
| `get_order_status` | `sales_order_number` | Auftragsnr., Kunde, Zahlungs-/Versandstatus, Summe, Tracking (10 Felder) |
| `search_customer_orders` | `customer_number` oder `email`, `limit` | Kundenstammdaten + Liste der Aufträge (6 Felder) |
| `check_article_stock` | `sku` | Artikel, VK netto, verfügbare Menge, Zulauf, Bestand je Lager (7 Felder) |
| `get_shipment_tracking` | `sales_order_number` | Lieferschein, Dienstleister, Tracking-ID, Versanddatum (8 Felder) |

### Zuordnung zu JTL-Wawi-Endpunkten

| Tool | JTL-Wawi-Endpunkt (GET) |
|---|---|
| `jtl_wawi_status` | `/feature` |
| `jtl_list_customers`, `jtl_get_customer` | `/customers`, `/customers/{id}` |
| `jtl_list_items`, `jtl_get_item` | `/items`, `/items/{id}` |
| `jtl_list_warehouses`, `jtl_get_item_stock` | `/warehouses`, `/stocks?itemId=…` |
| `jtl_list_sales_orders`, `jtl_get_sales_order` | `/salesOrders`, `/salesOrders/{id}` |
| `jtl_list_sales_order_line_items` | `/salesOrders/{id}/lineitems` |
| `jtl_list_shipments` | `/deliveryNotes` |
| `get_order_status` | `/salesOrders`, `/customers/{id}`, `/deliveryNotes` |
| `search_customer_orders` | `/customers`, `/salesOrders?customerId=…` |
| `check_article_stock` | `/items`, `/stocks?itemId=…`, `/warehouses` |
| `get_shipment_tracking` | `/deliveryNotes`, `/shippingMethods` |

Statusangaben werden als Text geliefert (LLM-freundlich):
Zahlungsstatus `unbezahlt` / `teilzahlung` / `bezahlt`,
Versandstatus `nicht_versendet` / `versendet` / `versendet_ohne_lieferschein`.

---

## 7. Anbindung an LiteLLM

Beispiel in `deploy/litellm_config.yaml.example`:

```yaml
mcp_servers:
  jtl_wawi:
    url: "http://10.10.10.20:8080/mcp"
    transport: "http"
    auth_type: "bearer_token"
    auth_value: "os.environ/JTL_MCP_AUTH_TOKEN"
    available_on_public_internet: false
```

Der Wert von `JTL_MCP_AUTH_TOKEN` muss identisch mit `MCP_SERVER_AUTH_TOKEN`
des MCP-Servers sein. Clients erreichen das Gateway danach unter
`http://<litellm-host>:4000/mcp` (Auth über `x-litellm-api-key`).

---

## 8. Betrieb (Deployment)

### Automatisiert (systemd)

```bash
sudo ./deploy/install.sh                 # Benutzer, venv, Unit, Dienst
sudo ./deploy/install.sh --no-start      # ohne Start
sudo ./deploy/uninstall.sh               # Dienst + Programm entfernen
sudo ./deploy/uninstall.sh --purge       # inkl. Konfiguration und Benutzer
```

Der Installer legt `/etc/jtl-mcp-server/.env` an (aus `.env.example`) – die
Zugangsdaten sind danach einzutragen.

### Betrieb im Proxmox-LXC

Detaillierte Anleitung (Container anlegen, Firewall, Netzwerk zur Wawi-API,
Absicherung): **`deploy/PROXMOX_LXC.md`**.

### Täglicher Betrieb

```bash
systemctl status jtl-mcp-server
journalctl -u jtl-mcp-server -f
systemctl restart jtl-mcp-server
```

### Healthcheck

```bash
MCP_SERVER_AUTH_TOKEN=<token> ./deploy/healthcheck.sh http://127.0.0.1:8080/mcp
```

Prüft, dass ohne Token `401` kommt und mit Token eine MCP-`initialize`-Anfrage
erfolgreich beantwortet wird (`Exit 0` = gesund).

---

## 9. Tests und Qualität

```bash
.venv/bin/python -m pytest -q          # 38 Tests (34 Unit + 4 E2E)
.venv/bin/python -m ruff check .       # Linting
```

Abgedeckt sind: Payload-Filterung und Feldbudget je Datensatz, Parameter-Mapping
der Listenabfragen, Status-Labels, base64-Bearer-Token an der JTL-API,
Fehler-Mapping (401/404/Timeout), Retry-Verhalten bei 5xx, die Read-only-Zusage
(kein Werkzeug schreibt, nur GET wird verwendet), die Bearer-Auth des
MCP-Servers (401 ohne/falsches Token) sowie die Vollständigkeit der
Tool-Registry. Der E2E-Test startet Prism und den FastMCP-Server als echte
Prozesse, ruft die JTL-Tools über einen echten MCP-HTTP-Client auf und prüft
den kompletten Roundtrip inklusive base64-Bearer-Token am Mock.

---

## 10. Lokaler Test & Live-Demo ohne JTL-Wawi (Prism Mock)

Für Vorführungen beim Arbeitgeber/Kunden und für Integrationstests ohne
laufende Windows-/JTL-Installation wird die offizielle JTL-ERP-OpenAPI-Spec
(`1.1.json`) mit **Stoplight Prism** als lokaler HTTP-Mock betrieben.

### 10.1 Einmalig vorbereiten

```bash
cd jtl-mcp-server

# Python-Umgebung (falls noch nicht vorhanden)
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"

# Offizielle Spec liegt bereits unter mock_env/jtl_erp_1.1.json.
# Demo-Spec mit deutschen B2B-Beispieldaten erzeugen:
python3 mock_env/seed_openapi.py
```

Für den Prism-Mock wird **Node.js >= 18** benötigt. Ohne Root-Rechte geht ein
portables Node.js:

```bash
mkdir -p .tools && cd .tools
curl -fsSL https://nodejs.org/dist/v22.22.1/node-v22.22.1-linux-x64.tar.xz \
  | tar -xJ --strip-components=1
cd ..
export JTL_MCP_NODE_BIN="$PWD/.tools/node/bin"
```

`start_demo.sh` und der E2E-Test suchen Node.js automatisch im `PATH`, in
`JTL_MCP_NODE_BIN` und in `.tools/node/bin`.

`seed_openapi.py` erzeugt `mock_env/jtl_erp_demo.json` und

* setzt den Basispfad `/api/eazybusiness/v1` vor alle Pfade (Prism ignoriert
  den `servers`-Block der Spec),
* ersetzt das OAuth2-Schema der Cloud-Spec durch ein HTTP-Bearer-Schema
  (on-prem JTL-Wawi sendet ein base64-kodiertes Bearer-Token),
* hinterlegt realistische Beispieldaten für Aufträge, Kunden, Artikel,
  Lagerbestände und Lieferscheine.

### 10.2 Demo starten

```bash
./mock_env/start_demo.sh
```

Das Skript startet Prism auf `http://127.0.0.1:5883` und den MCP-Server auf
`http://127.0.0.1:8099/mcp`, wartet auf beide Ports und gibt den fertigen
`curl`-Testbefehl sowie einen LiteLLM-Konfigurationsblock aus. Beenden mit
`Ctrl+C`; der `EXIT`-Trap räumt beide Prozesse auf.

### 10.3 curl-Tests

```bash
BASE64_TOKEN="$(printf '%s' '00000000-0000-0000-0000-000000000001' | base64 -w0)"

# Auftrag AU-2026-8841 direkt vom Prism-Mock
curl -sS -H "Authorization: Bearer ${BASE64_TOKEN}" \
  "http://127.0.0.1:5883/api/eazybusiness/v1/salesOrders?pageNumber=1&pageSize=50"

# Lieferschein LS-2026-9912 inkl. DHL-Tracking
curl -sS -H "Authorization: Bearer ${BASE64_TOKEN}" \
  "http://127.0.0.1:5883/api/eazybusiness/v1/deliveryNotes?salesOrderNumber=AU-2026-8841"

# MCP-Server: 401 ohne Token
curl -sS -o /dev/null -w '%{http_code}\n' -X POST \
  "http://127.0.0.1:8099/mcp" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"demo","version":"1.0"}}}'
# -> 401

# MCP-Server: initialize mit Token
curl -sS -X POST "http://127.0.0.1:8099/mcp" \
  -H "Authorization: Bearer demo-secret-token-123" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"demo","version":"1.0"}}}'
```

### 10.4 Automatisierter E2E-Test

```bash
.venv/bin/python -m pytest tests/test_e2e_prism.py -q -s
```

Der Test startet Prism, einen Recording-Proxy und den FastMCP-Server selbst,
ruft `tools/list` sowie die JTL-Tools über einen echten MCP-HTTP-Client auf und
prüft:

* `401` ohne bzw. mit falschem Bearer-Token am MCP-Server,
* base64-kodiertes Bearer-Token, das der JTL-Client an Prism sendet,
* die reduzierte deutsche Ausgabe (Auftrag, Kunde, Artikel, Bestand, Versand).

Eine Übergabe-Anweisung für externe Agenten (z. B. eine opencode-Instanz, die
den Connector gebaut hat) liegt unter `mock_env/OPENCODE_TESTANWEISUNG.md`.

### 10.5 Tool-Zuordnung der Demo-Szenarien

Die vier Support-Werkzeuge sind als eigene, anwendungsfallbezogene Tools
umgesetzt und rufen die JTL-API intern zusammen:

| Fachaufgabe | Tool | Argumente | Ergebnis |
|---|---|---|---|
| Auftragsstatus | `get_order_status` | `sales_order_number` | Auftragsnr., Kunde, Zahlungs-/Versandstatus, Summe, Tracking (10 Felder) |
| Kundenorders | `search_customer_orders` | `customer_number` oder `email` | Kundenstammdaten + Liste der Aufträge |
| Artikelbestand | `check_article_stock` | `sku` | Artikel, VK netto, verfügbare Menge, Zulauf, Bestand je Lager |
| Sendungsverfolgung | `get_shipment_tracking` | `sales_order_number` | Lieferschein, Dienstleister, Tracking-ID, Versanddatum |

Beispielaufrufe gegen die Demo-Umgebung:

```bash
# Session aufbauen (initialize)
SID=$(curl -sS -D - -o /dev/null -X POST "http://127.0.0.1:8099/mcp" \
  -H "Authorization: Bearer demo-secret-token-123" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"demo","version":"1.0"}}}' \
  | tr -d '\r' | awk -F': ' '/^mcp-session-id/ {print $2}')

curl -sS -X POST "http://127.0.0.1:8099/mcp" \
  -H "Authorization: Bearer demo-secret-token-123" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "mcp-session-id: ${SID}" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"get_order_status","arguments":{"sales_order_number":"AU-2026-8841"}}}'
```

### 10.6 Hinweis zur Demo-Spec

`mock_env/jtl_erp_demo.json` ist eine **aufbereitete Kopie** der offiziellen
Spec. Sie ist für den lokalen Mock gedacht und nicht für den Produktivbetrieb.
Die Original-Spec bleibt unverändert unter `mock_env/jtl_erp_1.1.json`.

---

## 11. Troubleshooting

| Symptom | Ursache / Lösung |
|---|---|
| `401` von JTL-Wawi | `JTL_API_KEY` prüfen; `JTL_API_KEY_B64` entsprechend setzen. |
| `404` vom MCP-Endpunkt | Falscher `MCP_PATH` oder falsche Port-/Pfad-Kombination. |
| `401` vom MCP-Server | `MCP_SERVER_AUTH_TOKEN` weicht vom Token des Clients ab. |
| `Zeitüberschreitung` | Erreichbarkeit der Wawi-API (Firewall, Port 5883) prüfen. |
| Leere Trefferlisten | `search` prüfen; `JTL_API_PATH` muss zur installierten Wawi-Version passen. |
| `Es wird ein gültiges Bearer-Token benötigt` | Token im Header `Authorization: Bearer <token>` senden. |

---

## 12. Referenzen

* JTL-Wawi REST-API (OpenAPI-Spec v1.1):
  <https://developer.jtl-software.com/openapi/erp/1.1.json>
* JTL-Wawi Entwicklerdokumentation:
  <https://developer.jtl-software.com/products/erpapi/openapi/>
* JTL-Wawi API – Instanz einrichten (JTL-Guide):
  <https://guide.jtl-software.com/jtl-wawi/jtl-wawi-api/instanz-der-jtl-wawi-api-mit-automatischem-start-einrichten/>
* FastMCP – HTTP Deployment:
  <https://gofastmcp.com/docs/deployment/http>
* LiteLLM – MCP Configuration Reference:
  <https://docs.litellm.ai/docs/mcp_config_reference>

## Lizenz

MIT
