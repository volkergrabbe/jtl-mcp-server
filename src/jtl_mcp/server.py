"""FastMCP-Server mit Bearer-Auth-Middleware und Read-only-Tools.

Der Server stellt ausschließlich Lesewerkzeuge bereit. Jedes Tool ruft die
JTL-Wawi-API ausschließlich per HTTP-GET auf und filtert die Antwort auf ein
schlankes, flaches JSON (max. 6-10 Felder je Datensatz), um den Kontext des
aufrufenden LLMs nicht zu überladen.
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from starlette.datastructures import Headers
from starlette.middleware import Middleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from .config import Settings, get_settings
from .jtl_client import JtlApiError, JtlClient
from .models import (
    ArticleStockResult,
    CustomerDetail,
    CustomerListResult,
    CustomerOrderSearchResult,
    CustomerSummary,
    ItemDetail,
    ItemListResult,
    ItemSummary,
    LineItem,
    LineItemListResult,
    OrderStatus,
    SalesOrderDetail,
    SalesOrderListResult,
    SalesOrderSummary,
    Shipment,
    ShipmentListResult,
    ShipmentTrackingResult,
    ShippingMethod,
    StatusResult,
    StockEntry,
    StockListResult,
    Warehouse,
    WarehouseListResult,
)

logger = logging.getLogger(__name__)

INSTRUCTIONS = """
Dieser Server liefert ausschliesslich Lesezugriffe auf JTL-Wawi-Daten
(Auftr\u00e4ge, Kunden, Artikel, Lagerbest\u00e4nde, Versandstatus).

Regeln fuer die Nutzung:
- Es gibt keine schreibenden Werkzeuge. Aktionen in JTL-Wawi (z. B. eine
  Bestellung anlegen oder stornieren) sind mit diesem Server nicht m\u00f6glich.
- Beginne mit Listenwerkzeugen (`jtl_list_*`), um IDs zu ermitteln, und hole
  danach mit den `jtl_get_*`-Werkzeugen die Details zu einem konkreten Satz.
- Die Antworten sind bewusst reduziert. Fehlende Felder stehen in der
  JTL-Wawi-API nicht zur Verf\u00fcgung oder wurden nicht angefordert.
- Statusangaben sind als Text codiert, z. B. Zahlungsstatus `bezahlt`,
  `teilzahlung` oder `unbezahlt`.
"""

mcp = FastMCP(name="jtl-wawi", instructions=INSTRUCTIONS)


class BearerAuthMiddleware:
    """ASGI-Middleware, die ein statisches Bearer-Token erzwingt.

    Der Token wird erst beim Eintreffen einer Anfrage aufgelöst, damit der
    Server-Import nicht von gültigen Umgebungsvariablen abh\u00e4ngt.
    """

    def __init__(self, app: ASGIApp, token_provider: Callable[[], str]) -> None:
        self.app = app
        self._token_provider = token_provider

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        scheme, _, credentials = headers.get("authorization", "").partition(" ")
        expected = self._token_provider()
        valid = (
            scheme.lower() == "bearer"
            and bool(credentials)
            and secrets.compare_digest(
                credentials.strip().encode("utf-8"), expected.encode("utf-8")
            )
        )
        if not valid:
            response = JSONResponse(
                {
                    "error": "unauthorized",
                    "message": "Es wird ein g\u00fcltiges Bearer-Token ben\u00f6tigt.",
                },
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


# --- Hilfsfunktionen --------------------------------------------------------


def _settings() -> Settings:
    return get_settings()


async def _with_client(action: Callable[[JtlClient], Awaitable[Any]]) -> Any:
    """F\u00fchrt eine API-Aktion aus und \u00fcbersetzt Fehler in ToolError."""

    try:
        async with JtlClient(_settings()) as client:
            return await action(client)
    except JtlApiError as exc:
        raise ToolError(str(exc)) from exc


def _limit(limit: int) -> int:
    settings = _settings()
    return max(1, min(limit, settings.jtl_max_page_size))


def _int_or_none(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# --- Werkzeuge --------------------------------------------------------------


@mcp.tool(tags={"diagnose"})
async def jtl_wawi_status() -> StatusResult:
    """Pr\u00fcft die Erreichbarkeit der JTL-Wawi-API und meldet die API-Version.

    Nutze dieses Werkzeug, wenn unklar ist, ob die Verbindung zur JTL-Wawi
    funktioniert (z. B. bei Timeouts oder leeren Ergebnissen).
    """

    settings = _settings()

    async def action(client: JtlClient) -> StatusResult:
        features = await client.get_json("/feature")
        versions = [
            version
            for version in (
                _int_or_none(item.get("Version")) if isinstance(item, Mapping) else None
                for item in (features if isinstance(features, list) else [])
            )
            if version is not None
        ]
        return StatusResult(
            api_base_url=settings.api_base_url,
            reachable=True,
            api_version=str(max(versions)) if versions else None,
            feature_count=len(features) if isinstance(features, list) else None,
        )

    try:
        return await _with_client(action)
    except ToolError as exc:
        return StatusResult(
            api_base_url=settings.api_base_url,
            reachable=False,
            error=str(exc),
        )


@mcp.tool(tags={"kunden"})
async def jtl_list_customers(
    search: str | None = None,
    customer_number: str | None = None,
    customer_group_id: int | None = None,
    limit: int = 50,
) -> CustomerListResult:
    """Listet Kunden aus JTL-Wawi (Lieferant, Nummer, Ort, E-Mail).

    Args:
        search: Freitextsuche \u00fcber Nummer, Name, Firma oder E-Mail.
        customer_number: Exakte Kundennummer.
        customer_group_id: ID der Kundengruppe (z. B. Händler).
        limit: Maximale Anzahl der Ergebnisse (1-200).
    """

    async def action(client: JtlClient) -> CustomerListResult:
        page = await client.get_paged(
            "/customers",
            {
                "searchKeyWord": search,
                "number": customer_number,
                "groupId": customer_group_id,
            },
            page_size=_limit(limit),
        )
        return CustomerListResult(
            count=len(page.items),
            total_items=page.total_items,
            customers=[CustomerSummary.from_api(item) for item in page.items],
        )

    return await _with_client(action)


@mcp.tool(tags={"kunden"})
async def jtl_get_customer(customer_id: int) -> CustomerDetail:
    """Liefert die Details eines Kunden (Anschriften, Kontaktdaten).

    Args:
        customer_id: Interne Kunden-ID aus `jtl_list_customers`.
    """

    async def action(client: JtlClient) -> CustomerDetail:
        payload = await client.get_json(f"/customers/{customer_id}")
        return CustomerDetail.from_api(payload)

    return await _with_client(action)


@mcp.tool(tags={"artikel"})
async def jtl_list_items(
    search: str | None = None,
    category_id: int | None = None,
    limit: int = 50,
) -> ItemListResult:
    """Listet Artikel aus dem Artikelstamm (ArtNr, Name, Preise, EAN).

    Args:
        search: Freitextsuche \u00fcber Artikelnummer, Name oder EAN.
        category_id: ID der Warengruppe.
        limit: Maximale Anzahl der Ergebnisse (1-200).
    """

    async def action(client: JtlClient) -> ItemListResult:
        page = await client.get_paged(
            "/items",
            {"searchKeyWord": search, "categoryId": category_id},
            page_size=_limit(limit),
        )
        return ItemListResult(
            count=len(page.items),
            total_items=page.total_items,
            items=[ItemSummary.from_api(item) for item in page.items],
        )

    return await _with_client(action)


@mcp.tool(tags={"artikel"})
async def jtl_get_item(item_id: int) -> ItemDetail:
    """Liefert die Details eines Artikels (Beschreibung, Preise, Gewicht).

    Args:
        item_id: Interne Artikel-ID aus `jtl_list_items`.
    """

    async def action(client: JtlClient) -> ItemDetail:
        payload = await client.get_json(f"/items/{item_id}")
        return ItemDetail.from_api(payload)

    return await _with_client(action)


@mcp.tool(tags={"lager"})
async def jtl_list_warehouses() -> WarehouseListResult:
    """Listet alle Lager aus JTL-Wawi (Name, Code, Typ)."""

    async def action(client: JtlClient) -> WarehouseListResult:
        page = await client.get_paged("/warehouses", page_size=_limit(200))
        return WarehouseListResult(
            count=len(page.items),
            warehouses=[Warehouse.from_api(item) for item in page.items],
        )

    return await _with_client(action)


@mcp.tool(tags={"lager"})
async def jtl_get_item_stock(item_id: int) -> StockListResult:
    """Liefert den Lagerbestand eines Artikels je Lager.

    Args:
        item_id: Interne Artikel-ID aus `jtl_list_items`.
    """

    async def action(client: JtlClient) -> StockListResult:
        page = await client.get_paged("/stocks", {"itemId": item_id}, page_size=_limit(200))
        warehouse_names = await _warehouse_names(client)

        return StockListResult(
            item_id=item_id,
            count=len(page.items),
            stocks=[StockEntry.from_api(item, warehouse_names) for item in page.items],
        )

    return await _with_client(action)


@mcp.tool(tags={"auftraege"})
async def jtl_list_sales_orders(
    sales_order_number: str | None = None,
    external_order_number: str | None = None,
    customer_id: int | None = None,
    created_since: str | None = None,
    created_until: str | None = None,
    is_cancelled: bool | None = None,
    limit: int = 50,
) -> SalesOrderListResult:
    """Listet Verkaufsauftr\u00e4ge (Nr., Kunde, Datum, Zahlungs-/Versandstatus).

    Args:
        sales_order_number: Exakte Auftragsnummer.
        external_order_number: Externe Auftragsnummer (z. B. Shop-Bestellnummer).
        customer_id: Interne Kunden-ID.
        created_since: Erstellt ab (ISO-Datum, z. B. 2026-01-01).
        created_until: Erstellt bis (ISO-Datum).
        is_cancelled: Auf stornierte Auftr\u00e4ge einschr\u00e4nken (True/False).
        limit: Maximale Anzahl der Ergebnisse (1-200).
    """

    async def action(client: JtlClient) -> SalesOrderListResult:
        page = await client.get_paged(
            "/salesOrders",
            {
                "salesOrderNumber": sales_order_number,
                "externalOrderNumber": external_order_number,
                "customerId": customer_id,
                "createdSince": created_since,
                "createdUntil": created_until,
                "isCancelled": is_cancelled,
            },
            page_size=_limit(limit),
        )
        return SalesOrderListResult(
            count=len(page.items),
            total_items=page.total_items,
            sales_orders=[SalesOrderSummary.from_api(item) for item in page.items],
        )

    return await _with_client(action)


@mcp.tool(tags={"auftraege"})
async def jtl_get_sales_order(sales_order_id: int) -> SalesOrderDetail:
    """Liefert die Details eines Verkaufsauftrags (Anschriften, Status, Summe).

    Args:
        sales_order_id: Interne Auftrags-ID aus `jtl_list_sales_orders`.
    """

    async def action(client: JtlClient) -> SalesOrderDetail:
        payload = await client.get_json(f"/salesOrders/{sales_order_id}")
        return SalesOrderDetail.from_api(payload)

    return await _with_client(action)


@mcp.tool(tags={"auftraege"})
async def jtl_list_sales_order_line_items(sales_order_id: int) -> LineItemListResult:
    """Listet die Positionen eines Verkaufsauftrags (Artikel, Menge, Preise).

    Args:
        sales_order_id: Interne Auftrags-ID aus `jtl_list_sales_orders`.
    """

    async def action(client: JtlClient) -> LineItemListResult:
        payload = await client.get_json(f"/salesOrders/{sales_order_id}/lineitems")
        items = payload if isinstance(payload, list) else []
        return LineItemListResult(
            count=len(items),
            line_items=[LineItem.from_api(item) for item in items],
        )

    return await _with_client(action)


@mcp.tool(tags={"versand"})
async def jtl_list_shipments(
    sales_order_number: str | None = None,
    customer_id: int | None = None,
    limit: int = 25,
) -> ShipmentListResult:
    """Liefert den Versandstatus je Paket (Sendungsnummer, Tracking, Datum).

    Args:
        sales_order_number: Auftragsnummer, auf die eingeschr\u00e4nkt wird.
        customer_id: Interne Kunden-ID, auf die eingeschr\u00e4nkt wird.
        limit: Maximale Anzahl der Lieferscheine (1-50).
    """

    max_notes = max(1, min(limit, 50))

    async def action(client: JtlClient) -> ShipmentListResult:
        page = await client.get_paged(
            "/deliveryNotes",
            {
                "salesOrderNumber": sales_order_number,
                "customerId": customer_id,
            },
            page_size=max_notes,
        )
        shipments: list[Shipment] = []
        for note in page.items:
            if not isinstance(note, Mapping):
                continue
            packages = note.get("Packages")
            if not isinstance(packages, list):
                continue
            for package in packages:
                if isinstance(package, Mapping):
                    shipments.append(Shipment.from_api(note, package))
        return ShipmentListResult(count=len(shipments), shipments=shipments)

    return await _with_client(action)


# --- Szenario-Werkzeuge ------------------------------------------------------
#
# Die Werkzeuge oben bilden die Datenfelder der JTL-Wawi ab. Die folgenden
# Werkzeuge bilden die typischen Support-Faelle ab und liefern die Antwort
# fertig aufbereitet in einem Durchgang.


async def _warehouse_names(client: JtlClient) -> dict[int, str]:
    """Liest die Lagernamen (fuer lesbare Bestandsausgaben)."""

    names: dict[int, str] = {}
    try:
        page = await client.get_paged("/warehouses", page_size=_limit(200))
        for raw in page.items:
            if isinstance(raw, Mapping):
                warehouse_id = _int_or_none(raw.get("Id"))
                name = raw.get("Name")
                if warehouse_id is not None and isinstance(name, str):
                    names[warehouse_id] = name
    except JtlApiError as exc:
        logger.warning("Lagerliste konnte nicht geladen werden: %s", exc)
    return names


async def _shipping_methods(client: JtlClient) -> dict[int, ShippingMethod]:
    """Liest die Versandarten (ID -> Versandart)."""

    methods: dict[int, ShippingMethod] = {}
    try:
        payload = await client.get_json("/shippingMethods")
    except JtlApiError as exc:
        logger.warning("Versandarten konnten nicht geladen werden: %s", exc)
        return methods

    raw_items: list[Any]
    if isinstance(payload, list):
        raw_items = payload
    elif isinstance(payload, Mapping):
        items = payload.get("Items")
        raw_items = list(items) if isinstance(items, list) else []
    else:
        raw_items = []

    for raw in raw_items:
        if isinstance(raw, Mapping):
            method = ShippingMethod.from_api(raw)
            if method.id:
                methods[method.id] = method
    return methods


@mcp.tool(tags={"support"})
async def get_order_status(sales_order_number: str) -> OrderStatus:
    """Liefert den Status eines Verkaufsauftrags als kompakte Übersicht.

    Beantwortet Support-Fragen wie "Wo bleibt die Bestellung AU-2026-8841?"
    mit Zahlungsstatus, Versandstatus, Kunde, Summe und Sendungsnummer.

    Args:
        sales_order_number: Auftragsnummer, z. B. "AU-2026-8841".
    """

    number = sales_order_number.strip()

    async def action(client: JtlClient) -> OrderStatus:
        page = await client.get_paged(
            "/salesOrders", {"salesOrderNumber": number}, page_size=_limit(10)
        )
        if not page.items:
            raise ToolError(f"Kein Auftrag mit der Nummer '{number}' gefunden.")
        order = SalesOrderSummary.from_api(page.items[0])

        customer_number: str | None = None
        customer_company: str | None = None
        if order.customer_id:
            try:
                customer = CustomerDetail.from_api(
                    await client.get_json(f"/customers/{order.customer_id}")
                )
                customer_number = customer.number
                customer_company = customer.company
            except JtlApiError as exc:
                logger.warning("Kundendaten konnten nicht geladen werden: %s", exc)

        tracking_id: str | None = None
        try:
            notes = await client.get_paged(
                "/deliveryNotes", {"salesOrderNumber": number}, page_size=_limit(10)
            )
            for note in notes.items:
                packages = note.get("Packages") if isinstance(note, Mapping) else None
                for package in packages or []:
                    if isinstance(package, Mapping) and package.get("TrackingID"):
                        tracking_id = str(package["TrackingID"])
                        break
                if tracking_id:
                    break
        except JtlApiError as exc:
            logger.warning("Lieferscheine konnten nicht geladen werden: %s", exc)

        return OrderStatus(
            order_number=order.number,
            customer_number=customer_number,
            customer_company=customer_company,
            order_date=order.order_date,
            payment_status=order.payment_status,
            delivery_status=order.delivery_status,
            is_paid=order.is_paid,
            total_gross=order.total_gross,
            currency=order.currency,
            tracking_id=tracking_id,
        )

    return await _with_client(action)


@mcp.tool(tags={"support"})
async def search_customer_orders(
    customer_number: str | None = None,
    email: str | None = None,
    limit: int = 20,
) -> CustomerOrderSearchResult:
    """Findet einen Kunden und listet seine Aufträge.

    Args:
        customer_number: Exakte Kundennummer, z. B. "KD-10420".
        email: E-Mail-Adresse des Kunden (Freitextsuche).
        limit: Maximale Anzahl der Aufträge (1-200).
    """

    async def action(client: JtlClient) -> CustomerOrderSearchResult:
        if customer_number:
            params: dict[str, Any] = {"number": customer_number.strip()}
        elif email:
            params = {"searchKeyWord": email.strip()}
        else:
            raise ToolError("Bitte 'customer_number' oder 'email' angeben.")

        page = await client.get_paged("/customers", params, page_size=_limit(10))
        if not page.items:
            return CustomerOrderSearchResult(order_count=0)

        customer = CustomerDetail.from_api(page.items[0])
        orders: list[SalesOrderSummary] = []
        if customer.id:
            order_page = await client.get_paged(
                "/salesOrders", {"customerId": customer.id}, page_size=_limit(limit)
            )
            orders = [SalesOrderSummary.from_api(item) for item in order_page.items]

        return CustomerOrderSearchResult(
            customer_number=customer.number,
            customer_company=customer.company,
            customer_email=customer.email,
            customer_city=customer.billing_address.city if customer.billing_address else None,
            order_count=len(orders),
            orders=orders,
        )

    return await _with_client(action)


@mcp.tool(tags={"support"})
async def check_article_stock(sku: str) -> ArticleStockResult:
    """Prüft Verfügbarkeit und Zulauf eines Artikels anhand der Artikelnummer.

    Args:
        sku: Artikelnummer, z. B. "ART-5001".
    """

    wanted = sku.strip().lower()

    async def action(client: JtlClient) -> ArticleStockResult:
        page = await client.get_paged(
            "/items", {"searchKeyWord": sku.strip()}, page_size=_limit(10)
        )
        if not page.items:
            raise ToolError(f"Kein Artikel mit der Nummer '{sku}' gefunden.")

        item = ItemSummary.from_api(page.items[0])
        for raw in page.items:
            candidate = ItemSummary.from_api(raw)
            if candidate.sku and candidate.sku.strip().lower() == wanted:
                item = candidate
                break

        stock_page = await client.get_paged(
            "/stocks", {"itemId": item.id}, page_size=_limit(200)
        )
        warehouse_names = await _warehouse_names(client)
        stocks = [StockEntry.from_api(raw, warehouse_names) for raw in stock_page.items]

        available = sum(entry.quantity_available or 0 for entry in stocks)
        incoming = sum(entry.quantity_incoming or 0 for entry in stocks)

        return ArticleStockResult(
            item_id=item.id,
            sku=item.sku,
            name=item.name,
            price_net=item.price_net,
            available_quantity=available,
            incoming_quantity=incoming,
            warehouses=stocks,
        )

    return await _with_client(action)


@mcp.tool(tags={"support"})
async def get_shipment_tracking(sales_order_number: str) -> ShipmentTrackingResult:
    """Liefert den Versandstatus eines Auftrags inklusive Sendungsnummer.

    Args:
        sales_order_number: Auftragsnummer, z. B. "AU-2026-8841".
    """

    number = sales_order_number.strip()

    async def action(client: JtlClient) -> ShipmentTrackingResult:
        page = await client.get_paged(
            "/deliveryNotes", {"salesOrderNumber": number}, page_size=_limit(20)
        )
        shipments: list[Shipment] = []
        for note in page.items:
            packages = note.get("Packages") if isinstance(note, Mapping) else None
            for package in packages or []:
                if isinstance(package, Mapping):
                    shipments.append(Shipment.from_api(note, package))

        if not shipments:
            raise ToolError(f"Für den Auftrag '{number}' wurde kein Lieferschein gefunden.")

        methods = await _shipping_methods(client)
        first = shipments[0]
        method = methods.get(first.shipping_method_id) if first.shipping_method_id else None

        return ShipmentTrackingResult(
            order_number=number,
            delivery_note_number=first.delivery_note_number,
            delivery_date=first.delivery_date,
            carrier=method.name if method else None,
            tracking_id=first.tracking_id,
            tracking_url=first.tracking_url,
            shipped_date=first.shipped_date,
            package_count=len(shipments),
        )

    return await _with_client(action)


# --- Betrieb ----------------------------------------------------------------


def create_app(settings: Settings | None = None):
    """Erzeugt die ASGI-App (f\u00fcr uvicorn bzw. Tests)."""

    resolved = settings or get_settings()
    return mcp.http_app(
        path=resolved.mcp_path,
        middleware=[
            Middleware(
                BearerAuthMiddleware,
                token_provider=lambda: resolved.mcp_auth_token,
            )
        ],
        stateless_http=resolved.mcp_stateless_http,
        host_origin_protection=True if resolved.mcp_allowed_hosts else None,
        allowed_hosts=resolved.mcp_allowed_hosts or None,
        allowed_origins=resolved.mcp_allowed_origins or None,
    )


def main() -> None:
    """Startet den HTTP-Server (Streamable HTTP, Port 8080, Pfad /mcp)."""

    settings = get_settings()
    logging.basicConfig(
        level=settings.mcp_log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger.info(
        "JTL-Wawi MCP-Server startet: MCP auf http://%s:%s%s | JTL-API: %s",
        settings.mcp_host,
        settings.mcp_port,
        settings.mcp_path,
        settings.api_base_url,
    )
    mcp.run(
        transport="http",
        host=settings.mcp_host,
        port=settings.mcp_port,
        path=settings.mcp_path,
        log_level=settings.mcp_log_level.lower(),
        stateless_http=settings.mcp_stateless_http,
        middleware=[
            Middleware(
                BearerAuthMiddleware,
                token_provider=lambda: settings.mcp_auth_token,
            )
        ],
        host_origin_protection=True if settings.mcp_allowed_hosts else None,
        allowed_hosts=settings.mcp_allowed_hosts or None,
        allowed_origins=settings.mcp_allowed_origins or None,
    )


if __name__ == "__main__":  # pragma: no cover
    main()
