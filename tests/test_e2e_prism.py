"""End-to-End-Integrationstest gegen Stoplight Prism.

Der Test startet

1. einen echten **Prism-Mock** (``@stoplight/prism-cli``) auf Basis der
   aufbereiteten JTL-OpenAPI-Demo-Spec,
2. einen kleinen **Recording-Proxy** zwischen MCP-Server und Prism, der die
   Authorization-Header mitschreibt (Nachweis: base64-kodiertes Bearer-Token),
3. den **FastMCP-Server** als echten HTTP-Prozess.

Anschließend wird über den offiziellen MCP-Streamable-HTTP-Client mit
``Authorization: Bearer ...`` auf die Tools zugegriffen.

Der Test ist bewusst ein Integrationstest und benötigt ``npx`` (Node.js).
Fehlt ``npx``, wird der Test mit einer klaren Meldung übersprungen.
"""

from __future__ import annotations

import base64
import contextlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MOCK_ENV = PROJECT_ROOT / "mock_env"
DEMO_SPEC = MOCK_ENV / "jtl_erp_demo.json"
SEED_SCRIPT = MOCK_ENV / "seed_openapi.py"

API_PATH = "/api/eazybusiness/v1"
JTL_API_KEY = "00000000-0000-0000-0000-000000000001"
MCP_TOKEN = "demo-secret-token-123"
PRISM_PACKAGE = "@stoplight/prism-cli@5.14.2"

# Authorization-Header, die der Proxy gesehen hat.
_PROXY_AUTHORIZATIONS: list[str | None] = []


# --- Hilfsfunktionen --------------------------------------------------------


def _node_bin_dir() -> str | None:
    """Findet ein Node.js-Binary (PATH, JTL_MCP_NODE_BIN oder lokales .tools)."""

    candidates = [
        os.environ.get("JTL_MCP_NODE_BIN"),
        shutil.which("npx"),
        str(PROJECT_ROOT / ".tools" / "node" / "bin"),
        str(PROJECT_ROOT.parent / ".tools" / "node" / "bin"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        if Path(candidate).is_file() and Path(candidate).name == "npx":
            return str(Path(candidate).parent)
        if Path(candidate).is_dir() and (Path(candidate) / "npx").is_file():
            return candidate
    return None


def _npx_env() -> dict[str, str]:
    """Umgebung für npx - mit Node-Bin-Verzeichnis im PATH."""

    env = dict(os.environ)
    node_bin = _node_bin_dir()
    if node_bin:
        env["PATH"] = f"{node_bin}{os.pathsep}{env.get('PATH', '')}"
    return env


def _free_port() -> int:
    """Ermittelt einen freien TCP-Port auf 127.0.0.1."""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_port(port: int, *, timeout: float = 120.0) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError as exc:  # pragma: no cover - Zeitablauf ist der Fehlerfall
            last_error = exc
            time.sleep(0.25)
    raise RuntimeError(f"Port {port} wurde nicht rechtzeitig erreichbar: {last_error}")


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    """Beendet einen Prozess samt Kindprozessen (npx spawnt einen Node-Prozess)."""

    if process.poll() is not None:
        return
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        process.wait(timeout=5)


class _RecordingProxyHandler(BaseHTTPRequestHandler):
    """Leitet Requests an Prism weiter und protokolliert Authorization-Header."""

    protocol_version = "HTTP/1.1"

    def _forward(self) -> None:
        _PROXY_AUTHORIZATIONS.append(self.headers.get("Authorization"))

        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        target = f"http://127.0.0.1:{self.server.prism_port}{self.path}"  # type: ignore[attr-defined]

        request = urllib.request.Request(target, data=body, method=self.command)
        for name, value in self.headers.items():
            if name.lower() in {"host", "content-length", "connection"}:
                continue
            request.add_header(name, value)

        try:
            with urllib.request.urlopen(request, timeout=15) as upstream:
                payload = upstream.read()
                self._relay(upstream.status, upstream.headers.items(), payload)
        except urllib.error.HTTPError as exc:
            self._relay(exc.code, exc.headers.items(), exc.read())
        except Exception as exc:
            payload = json.dumps({"error": "proxy", "detail": str(exc)}).encode()
            self._relay(502, [("Content-Type", "application/json")], payload)

    def _relay(self, status: int, headers: Iterator[tuple[str, str]], payload: bytes) -> None:
        self.send_response(status)
        for name, value in headers:
            if name.lower() in {"transfer-encoding", "connection", "content-length"}:
                continue
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = _forward  # type: ignore[assignment]
    do_POST = _forward  # type: ignore[assignment]

    def log_message(self, format: str, *args: object) -> None:
        """Proxy-Logs unterdrücken (der Test soll leise bleiben)."""


class _ProxyServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    prism_port: int


def _start_prism(port: int) -> subprocess.Popen[bytes]:
    """Startet Prism als eigenen Prozess."""

    node_bin = _node_bin_dir()
    if not node_bin:
        raise RuntimeError("npx nicht gefunden")
    npx = str(Path(node_bin) / "npx")
    return subprocess.Popen(
        [
            npx,
            "--yes",
            PRISM_PACKAGE,
            "mock",
            "-h",
            "127.0.0.1",
            "-p",
            str(port),
            str(DEMO_SPEC),
        ],
        cwd=str(PROJECT_ROOT),
        env=_npx_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def _start_mcp_server(port: int, jtl_base_url: str) -> subprocess.Popen[bytes]:
    """Startet den FastMCP-Server als eigenen Prozess."""

    env = {
        **os.environ,
        "PYTHONPATH": str(PROJECT_ROOT / "src"),
        "JTL_BASE_URL": jtl_base_url,
        "JTL_API_PATH": API_PATH,
        "JTL_API_KEY": JTL_API_KEY,
        "MCP_SERVER_AUTH_TOKEN": MCP_TOKEN,
        "MCP_HOST": "127.0.0.1",
        "MCP_PORT": str(port),
        "MCP_PATH": "/mcp",
        "MCP_LOG_LEVEL": "WARNING",
    }
    return subprocess.Popen(
        [sys.executable, "-m", "jtl_mcp"],
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


# --- Fixture ----------------------------------------------------------------


@pytest.fixture(scope="module")
def prism_stack() -> Iterator[dict[str, object]]:
    """Startet Prism + Recording-Proxy + MCP-Server und räumt danach auf."""

    if not _node_bin_dir():
        pytest.skip("npx (Node.js) ist nicht installiert - Prism-E2E-Test übersprungen")

    if not DEMO_SPEC.is_file():
        subprocess.run(
            [sys.executable, str(SEED_SCRIPT)],
            cwd=str(PROJECT_ROOT),
            check=True,
            capture_output=True,
            text=True,
        )

    prism_port = _free_port()
    proxy_port = _free_port()
    mcp_port = _free_port()
    _PROXY_AUTHORIZATIONS.clear()

    prism = _start_prism(prism_port)
    proxy = _ProxyServer(("127.0.0.1", proxy_port), _RecordingProxyHandler)
    proxy.prism_port = prism_port  # type: ignore[attr-defined]
    proxy_thread = threading.Thread(target=proxy.serve_forever, daemon=True)
    proxy_thread.start()

    mcp = _start_mcp_server(mcp_port, f"http://127.0.0.1:{proxy_port}")
    try:
        _wait_for_port(prism_port)
        _wait_for_port(mcp_port)
        yield {
            "prism_port": prism_port,
            "proxy_port": proxy_port,
            "mcp_port": mcp_port,
            "mcp_url": f"http://127.0.0.1:{mcp_port}/mcp",
        }
    finally:
        _stop_process(mcp)
        _stop_process(prism)
        proxy.shutdown()
        proxy.server_close()


# --- Tests ------------------------------------------------------------------


def test_unauthenticated_mcp_request_returns_401(prism_stack: dict[str, object]) -> None:
    """Ohne Bearer-Token muss der MCP-Server mit HTTP 401 antworten."""

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "e2e-test", "version": "1.0"},
        },
    }
    response = httpx.post(
        str(prism_stack["mcp_url"]),
        json=payload,
        headers={"Accept": "application/json, text/event-stream"},
        timeout=10,
    )
    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"
    assert response.headers["www-authenticate"] == "Bearer"


def test_wrong_bearer_token_returns_401(prism_stack: dict[str, object]) -> None:
    """Ein falsches Bearer-Token muss ebenfalls abgewiesen werden."""

    response = httpx.post(
        str(prism_stack["mcp_url"]),
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        headers={
            "Accept": "application/json, text/event-stream",
            "Authorization": "Bearer falsches-token",
        },
        timeout=10,
    )
    assert response.status_code == 401


async def test_mcp_tools_roundtrip_against_prism(prism_stack: dict[str, object]) -> None:
    """Ruft die JTL-Tools über einen echten MCP-HTTP-Client gegen Prism auf."""

    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport

    transport = StreamableHttpTransport(
        str(prism_stack["mcp_url"]),
        headers={"Authorization": f"Bearer {MCP_TOKEN}"},
    )

    async with Client(transport) as client:
        tools = await client.list_tools()
        tool_names = {tool.name for tool in tools}
        assert {
            "jtl_wawi_status",
            "jtl_list_customers",
            "jtl_list_items",
            "jtl_list_sales_orders",
            "jtl_get_item_stock",
            "jtl_list_shipments",
        } <= tool_names

        status = await client.call_tool("jtl_wawi_status")
        status_data = _structured(status)
        assert status_data["reachable"] is True
        assert status_data["api_version"] == "1"
        assert status_data["feature_count"] == 4

        orders = _structured(
            await client.call_tool(
                "jtl_list_sales_orders", {"sales_order_number": "AU-2026-8841"}
            )
        )
        assert orders["count"] == 1
        order = orders["sales_orders"][0]
        assert order["number"] == "AU-2026-8841"
        assert order["customer_id"] == 10420
        assert order["payment_status"] == "bezahlt"
        assert order["delivery_status"] == "versendet"
        assert order["total_gross"] == 1489.5
        assert order["currency"] == "EUR"
        assert order["is_cancelled"] is False

        customers = _structured(
            await client.call_tool("jtl_list_customers", {"search": "Musterbau"})
        )
        assert customers["count"] == 1
        customer = customers["customers"][0]
        assert customer["number"] == "KD-10420"
        assert customer["company"] == "Musterbau GmbH"
        assert customer["email"] == "einkauf@musterbau-gmbh.de"
        assert customer["city"] == "Bückeburg"

        items = _structured(await client.call_tool("jtl_list_items", {"search": "ART-5001"}))
        assert items["count"] == 1
        item = items["items"][0]
        assert item["sku"] == "ART-5001"
        assert item["name"] == "Industrie-Steuerungsmodul Pro X2"
        assert item["price_net"] == 249.0
        assert item["is_active"] is True

        stock = _structured(await client.call_tool("jtl_get_item_stock", {"item_id": 5001}))
        assert stock["count"] == 1
        entry = stock["stocks"][0]
        assert entry["quantity_total"] == 142.0
        assert entry["quantity_locked_for_shipment"] == 100.0
        assert entry["quantity_available"] == 42.0
        assert entry["warehouse_name"] == "Hauptlager Bückeburg"

        shipments = _structured(
            await client.call_tool(
                "jtl_list_shipments", {"sales_order_number": "AU-2026-8841"}
            )
        )
        assert shipments["count"] == 1
        shipment = shipments["shipments"][0]
        assert shipment["delivery_note_number"] == "LS-2026-9912"
        assert shipment["tracking_id"] == "00340434161094012345"
        assert shipment["delivery_date"] == "2026-11-12T07:30:00+01:00"

    # Der Proxy hat die Requests des JTL-Clients gesehen und das base64-kodierte
    # Bearer-Token unverändert an Prism weitergegeben.
    expected = "Bearer " + base64.b64encode(JTL_API_KEY.encode()).decode()
    assert _PROXY_AUTHORIZATIONS, "Der Proxy hat keine JTL-Requests gesehen"
    assert set(_PROXY_AUTHORIZATIONS) == {expected}


async def test_scenario_tools_against_prism(prism_stack: dict[str, object]) -> None:
    """Die vier Support-Werkzeuge liefern die deutschen Demodaten."""

    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport

    transport = StreamableHttpTransport(
        str(prism_stack["mcp_url"]),
        headers={"Authorization": f"Bearer {MCP_TOKEN}"},
    )

    async with Client(transport) as client:
        tools = await client.list_tools()
        names = {tool.name for tool in tools}
        assert {
            "get_order_status",
            "search_customer_orders",
            "check_article_stock",
            "get_shipment_tracking",
        } <= names

        status = _structured(
            await client.call_tool("get_order_status", {"sales_order_number": "AU-2026-8841"})
        )
        assert status["order_number"] == "AU-2026-8841"
        assert status["customer_number"] == "KD-10420"
        assert status["customer_company"] == "Musterbau GmbH"
        assert status["payment_status"] == "bezahlt"
        assert status["delivery_status"] == "versendet"
        assert status["is_paid"] is True
        assert status["total_gross"] == 1489.5
        assert status["currency"] == "EUR"
        assert status["tracking_id"] == "00340434161094012345"
        assert len(status) <= 10

        orders = _structured(
            await client.call_tool("search_customer_orders", {"customer_number": "KD-10420"})
        )
        assert orders["customer_number"] == "KD-10420"
        assert orders["customer_company"] == "Musterbau GmbH"
        assert orders["customer_email"] == "einkauf@musterbau-gmbh.de"
        assert orders["customer_city"] == "Bückeburg"
        assert orders["order_count"] == 1
        assert orders["orders"][0]["number"] == "AU-2026-8841"

        stock = _structured(await client.call_tool("check_article_stock", {"sku": "ART-5001"}))
        assert stock["sku"] == "ART-5001"
        assert stock["name"] == "Industrie-Steuerungsmodul Pro X2"
        assert stock["price_net"] == 249.0
        assert stock["available_quantity"] == 42.0
        assert stock["incoming_quantity"] == 100.0
        assert stock["warehouses"][0]["warehouse_name"] == "Hauptlager Bückeburg"

        shipment = _structured(
            await client.call_tool("get_shipment_tracking", {"sales_order_number": "AU-2026-8841"})
        )
        assert shipment["order_number"] == "AU-2026-8841"
        assert shipment["delivery_note_number"] == "LS-2026-9912"
        assert shipment["carrier"] == "DHL Paket"
        assert shipment["tracking_id"] == "00340434161094012345"
        assert shipment["package_count"] == 1

    # Die Antworten enthalten nur die schlanken Ausgabefelder - keine
    # internen JTL-Metafelder wie PaymentDetails oder BillingAddress.
    payload = json.dumps({"status": status, "orders": orders, "stock": stock})
    for internal_field in (
        "PaymentDetails",
        "ShippingDetail",
        "BillingAddress",
        "Shipmentaddress",
        "ItemPriceData",
        "Identifiers",
        "TotalItems",
    ):
        assert internal_field not in payload


def _structured(result: object) -> dict[str, object]:
    """Liest das strukturierte Ergebnis eines MCP-Tool-Aufrufs."""

    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured
    content = getattr(result, "content", None)
    if content:
        text = getattr(content[0], "text", None)
        if text:
            return json.loads(text)
    raise AssertionError(f"Kein strukturiertes Ergebnis: {result!r}")
