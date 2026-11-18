"""Unit-Tests für die MCP-Tools, den HTTP-Client und die Bearer-Auth.

Die JTL-Wawi-API wird vollständig mit respx gemockt; es findet keine echte
Netzwerkkommunikation statt.
"""

from __future__ import annotations

import base64
from typing import Any

import httpx
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from pydantic import BaseModel

from jtl_mcp import models
from jtl_mcp.jtl_client import JtlClient, JtlReadOnlyViolation
from jtl_mcp.models import (
    ArticleStockResult,
    CustomerDetail,
    CustomerListResult,
    CustomerOrderSearchResult,
    ItemDetail,
    ItemListResult,
    LineItemListResult,
    OrderStatus,
    SalesOrderDetail,
    SalesOrderListResult,
    ShipmentListResult,
    ShipmentTrackingResult,
    StatusResult,
    StockListResult,
    WarehouseListResult,
)
from jtl_mcp.server import BearerAuthMiddleware, create_app, mcp

from .mock_data import (
    CUSTOMER_1,
    CUSTOMERS_PAGE,
    DELIVERY_NOTES_PAGE,
    DEMO_CUSTOMER,
    DEMO_CUSTOMERS_PAGE,
    DEMO_DELIVERY_NOTES_PAGE,
    DEMO_ITEMS_PAGE,
    DEMO_SALES_ORDERS_PAGE,
    DEMO_SHIPPING_METHODS,
    DEMO_STOCKS_PAGE,
    DEMO_WAREHOUSES_PAGE,
    ERROR_NOT_FOUND,
    ERROR_UNAUTHORIZED,
    FEATURES,
    ITEM_1,
    ITEMS_PAGE,
    SALES_ORDER_1,
    SALES_ORDER_LINE_ITEMS,
    SALES_ORDERS_PAGE,
    STOCKS_PAGE,
    WAREHOUSES_PAGE,
)


async def invoke(
    name: str,
    arguments: dict[str, Any] | None = None,
    model: type[BaseModel] | None = None,
) -> Any:
    """Ruft ein Tool über die öffentliche FastMCP-API auf."""

    result = await mcp.call_tool(name, arguments or {})
    assert result.is_error is False
    payload = result.structured_content
    if model is None:
        return payload
    assert payload is not None, f"Tool {name} lieferte kein strukturiertes Ergebnis"
    return model.model_validate(payload)


# ---------------------------------------------------------------------------
# Kunden
# ---------------------------------------------------------------------------


async def test_list_customers_returns_compact_records(api):
    route = api.get("/customers").mock(return_value=httpx.Response(200, json=CUSTOMERS_PAGE))

    result = await invoke("jtl_list_customers", model=CustomerListResult)

    assert route.called
    assert result.count == 2
    assert result.total_items == 2

    first = result.customers[0]
    assert first.id == 42
    assert first.number == "10001"
    assert first.company == "Muster Handels GmbH"
    assert first.contact_name == "Max Mustermann"
    assert first.city == "München"
    assert first.email == "einkauf@muster-handel.de"

    # Interne Metafelder dürfen nicht durchsickern.
    payload = first.model_dump()
    assert set(payload) == {
        "id",
        "number",
        "company",
        "contact_name",
        "city",
        "email",
        "customer_group_id",
        "customer_since",
    }
    assert "PaymentSettings" not in payload
    assert len(payload) <= 10


async def test_list_customers_forwards_search_parameters(api):
    route = api.get("/customers").mock(return_value=httpx.Response(200, json=CUSTOMERS_PAGE))

    await invoke(
        "jtl_list_customers",
        {"search": "Muster", "customer_number": "10001", "customer_group_id": 3, "limit": 10},
    )

    request = route.calls.last.request
    assert request.method == "GET"
    query = dict(request.url.params)
    assert query["searchKeyWord"] == "Muster"
    assert query["number"] == "10001"
    assert query["groupId"] == "3"
    assert query["pageSize"] == "10"
    assert query["pageNumber"] == "1"


async def test_get_customer_returns_addresses(api):
    api.get("/customers/42").mock(return_value=httpx.Response(200, json=CUSTOMER_1))

    result = await invoke("jtl_get_customer", {"customer_id": 42}, CustomerDetail)

    assert result.id == 42
    assert result.phone == "+49 89 1234567"
    assert result.billing_address is not None
    assert result.billing_address.street == "Hauptstraße 12"
    assert result.billing_address.postal_code == "80331"
    assert result.shipment_address is not None
    assert result.shipment_address.city == "Hallbergmoos"
    assert len(result.model_dump()) <= 10


# ---------------------------------------------------------------------------
# Artikel
# ---------------------------------------------------------------------------


async def test_list_items_filters_price_and_identifier(api):
    api.get("/items").mock(return_value=httpx.Response(200, json=ITEMS_PAGE))

    result = await invoke("jtl_list_items", model=ItemListResult)

    assert result.count == 2
    item = result.items[0]
    assert item.sku == "ART-1001"
    assert item.name == "Industrieschraube M8x40"
    assert item.price_net == 0.35
    assert item.suggested_retail_price == 0.99
    assert item.gtin == "4001234567890"
    assert item.manufacturer_number == "MAN-0812"
    assert len(item.model_dump()) <= 10
    assert "ItemPriceData" not in item.model_dump()
    assert "Dimensions" not in item.model_dump()


async def test_get_item_returns_detail(api):
    api.get("/items/501").mock(return_value=httpx.Response(200, json=ITEM_1))

    result = await invoke("jtl_get_item", {"item_id": 501}, ItemDetail)

    assert result.id == 501
    assert result.purchase_price_net == 0.12
    assert result.shipping_weight == 0.025
    assert result.item_weight == 0.021
    assert len(result.model_dump()) <= 10


# ---------------------------------------------------------------------------
# Lager
# ---------------------------------------------------------------------------


async def test_get_item_stock_resolves_warehouse_names(api):
    api.get("/stocks").mock(return_value=httpx.Response(200, json=STOCKS_PAGE))
    api.get("/warehouses").mock(return_value=httpx.Response(200, json=WAREHOUSES_PAGE))

    result = await invoke("jtl_get_item_stock", {"item_id": 501}, StockListResult)

    assert result.item_id == 501
    assert result.count == 2

    first = result.stocks[0]
    assert first.warehouse_id == 1
    assert first.warehouse_name == "Hauptlager"
    assert first.storage_location == "Regal A-01"
    assert first.quantity_total == 1200
    assert first.quantity_locked_for_shipment == 200
    assert first.quantity_available == 1000
    assert len(first.model_dump()) <= 10


async def test_list_warehouses(api):
    api.get("/warehouses").mock(return_value=httpx.Response(200, json=WAREHOUSES_PAGE))

    result = await invoke("jtl_list_warehouses", model=WarehouseListResult)

    assert result.count == 2
    assert result.warehouses[0].name == "Hauptlager"
    assert result.warehouses[0].type == "Standardlager"
    assert result.warehouses[0].is_active is True


# ---------------------------------------------------------------------------
# Auftraege
# ---------------------------------------------------------------------------


async def test_list_sales_orders_maps_status_labels(api):
    route = api.get("/salesOrders").mock(
        return_value=httpx.Response(200, json=SALES_ORDERS_PAGE)
    )

    result = await invoke(
        "jtl_list_sales_orders",
        {"customer_id": 42, "created_since": "2026-11-01", "is_cancelled": False},
        SalesOrderListResult,
    )

    query = dict(route.calls.last.request.url.params)
    assert query["customerId"] == "42"
    assert query["createdSince"] == "2026-11-01"
    assert query["isCancelled"] == "false"

    assert result.count == 2
    first = result.sales_orders[0]
    assert first.number == "2026-100234"
    assert first.customer_id == 42
    assert first.payment_status == "bezahlt"
    assert first.delivery_status == "versendet"
    assert first.total_gross == 476.28
    assert first.currency == "EUR"
    assert first.is_cancelled is False
    assert len(first.model_dump()) <= 10

    second = result.sales_orders[1]
    assert second.payment_status == "unbezahlt"
    assert second.delivery_status == "nicht_versendet"


async def test_get_sales_order_returns_addresses(api):
    api.get("/salesOrders/9001").mock(return_value=httpx.Response(200, json=SALES_ORDER_1))

    result = await invoke("jtl_get_sales_order", {"sales_order_id": 9001}, SalesOrderDetail)

    assert result.id == 9001
    assert result.billing_address is not None
    assert result.billing_address.city == "München"
    assert result.shipment_address is not None
    assert result.shipment_address.city == "Hallbergmoos"
    assert len(result.model_dump()) <= 10


async def test_list_sales_order_line_items(api):
    api.get("/salesOrders/9001/lineitems").mock(
        return_value=httpx.Response(200, json=SALES_ORDER_LINE_ITEMS)
    )

    result = await invoke(
        "jtl_list_sales_order_line_items",
        {"sales_order_id": 9001},
        LineItemListResult,
    )

    assert result.count == 2
    first = result.line_items[0]
    assert first.sku == "ART-1001"
    assert first.quantity == 1000
    assert first.quantity_delivered == 1000
    assert first.price_net == 0.35
    assert first.price_gross == 0.42
    assert first.tax_rate == 19.0
    assert first.item_type == "artikel"
    assert result.line_items[1].item_type == "versand"
    assert len(first.model_dump()) <= 10


# ---------------------------------------------------------------------------
# Versand
# ---------------------------------------------------------------------------


async def test_list_shipments_flattens_packages(api):
    route = api.get("/deliveryNotes").mock(
        return_value=httpx.Response(200, json=DELIVERY_NOTES_PAGE)
    )

    result = await invoke(
        "jtl_list_shipments",
        {"sales_order_number": "2026-100234"},
        ShipmentListResult,
    )

    assert route.calls.last.request.url.params["salesOrderNumber"] == "2026-100234"
    assert result.count == 1
    shipment = result.shipments[0]
    assert shipment.delivery_note_number == "LS-2026-0042"
    assert shipment.tracking_id == "00340434161234567890"
    assert shipment.tracking_url.endswith("00340434161234567890")
    assert shipment.shipped_date == "2026-11-05T18:00:00"
    assert shipment.weight == 12.5
    assert len(shipment.model_dump()) <= 10


# ---------------------------------------------------------------------------
# Betriebsstatus
# ---------------------------------------------------------------------------


async def test_status_tool_reports_reachable_api(api):
    api.get("/feature").mock(return_value=httpx.Response(200, json=FEATURES))

    result = await invoke("jtl_wawi_status", model=StatusResult)

    assert result.reachable is True
    assert result.feature_count == 3
    assert result.api_version == "1"
    assert result.error is None


async def test_status_tool_reports_unreachable_api(api):
    api.get("/feature").mock(return_value=httpx.Response(500, json={"title": "Boom"}))

    result = await invoke("jtl_wawi_status", model=StatusResult)

    assert result.reachable is False
    assert result.error is not None


# ---------------------------------------------------------------------------
# HTTP-Client: Auth, Fehler, Retries
# ---------------------------------------------------------------------------


async def test_request_carries_base64_bearer_token(api, settings):
    route = api.get("/customers").mock(return_value=httpx.Response(200, json=CUSTOMERS_PAGE))

    await invoke("jtl_list_customers")

    expected = base64.b64encode(settings.jtl_api_key.get_secret_value().encode()).decode()
    assert route.calls.last.request.headers["authorization"] == f"Bearer {expected}"


async def test_unauthorized_response_raises_tool_error(api):
    api.get("/customers").mock(return_value=httpx.Response(401, json=ERROR_UNAUTHORIZED))

    with pytest.raises(ToolError) as excinfo:
        await invoke("jtl_list_customers")

    assert "Authentifizierung" in str(excinfo.value)


async def test_not_found_raises_tool_error(api):
    api.get("/customers/999").mock(return_value=httpx.Response(404, json=ERROR_NOT_FOUND))

    with pytest.raises(ToolError) as excinfo:
        await invoke("jtl_get_customer", {"customer_id": 999})

    assert "nicht gefunden" in str(excinfo.value)


async def test_server_error_is_retried_and_then_succeeds(api):
    route = api.get("/customers").mock(
        side_effect=[
            httpx.Response(503, json={"title": "temporarily unavailable"}),
            httpx.Response(200, json=CUSTOMERS_PAGE),
        ]
    )

    result = await invoke("jtl_list_customers", model=CustomerListResult)

    assert route.call_count == 2
    assert result.count == 2


async def test_timeout_is_reported_as_tool_error(api):
    api.get("/customers").mock(side_effect=httpx.ReadTimeout("timeout"))

    with pytest.raises(ToolError) as excinfo:
        await invoke("jtl_list_customers")

    assert "Zeitüberschreitung" in str(excinfo.value)


async def test_client_refuses_write_methods(settings):
    async with JtlClient(settings) as client:
        with pytest.raises(JtlReadOnlyViolation):
            await client._request("POST", "/customers")
        with pytest.raises(JtlReadOnlyViolation):
            await client._request("DELETE", "/customers/1")

    public_methods = {
        name
        for name in dir(JtlClient)
        if not name.startswith("_") and callable(getattr(JtlClient, name))
    }
    assert public_methods <= {"get_json", "get_paged", "aclose"}


async def test_every_tool_call_uses_get_only(api):
    api.get("/customers").mock(return_value=httpx.Response(200, json=CUSTOMERS_PAGE))
    api.get("/items").mock(return_value=httpx.Response(200, json=ITEMS_PAGE))
    api.get("/warehouses").mock(return_value=httpx.Response(200, json=WAREHOUSES_PAGE))
    api.get("/stocks").mock(return_value=httpx.Response(200, json=STOCKS_PAGE))
    api.get("/salesOrders").mock(return_value=httpx.Response(200, json=SALES_ORDERS_PAGE))
    api.get("/deliveryNotes").mock(return_value=httpx.Response(200, json=DELIVERY_NOTES_PAGE))

    await invoke("jtl_list_customers")
    await invoke("jtl_list_items")
    await invoke("jtl_list_warehouses")
    await invoke("jtl_get_item_stock", {"item_id": 501})
    await invoke("jtl_list_sales_orders")
    await invoke("jtl_list_shipments")

    assert api.calls.call_count > 0
    assert all(call.request.method == "GET" for call in api.calls)


# ---------------------------------------------------------------------------
# Bearer-Auth des MCP-Servers
# ---------------------------------------------------------------------------


async def test_bearer_middleware_rejects_request_without_token(settings):
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://mcp.test") as client:
        response = await client.get("/mcp")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


async def test_bearer_middleware_rejects_wrong_token(settings):
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://mcp.test") as client:
        response = await client.get("/mcp", headers={"Authorization": "Bearer falsches-token"})

    assert response.status_code == 401


async def _asgi_ok(scope, receive, send):
    """Minimaler ASGI-Responder für die Middleware-Tests."""

    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


async def test_bearer_middleware_accepts_valid_token():
    calls: list[str] = []

    async def downstream(scope, receive, send):
        calls.append(scope["path"])
        await _asgi_ok(scope, receive, send)

    app = BearerAuthMiddleware(downstream, token_provider=lambda: "geheim-token")
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://mcp.test") as client:
        response = await client.get("/mcp", headers={"Authorization": "Bearer geheim-token"})

    assert response.status_code == 200
    assert calls == ["/mcp"]


async def test_bearer_middleware_survives_non_ascii_token():
    """Nicht-ASCII-Token dürfen den Vergleich nicht zum Absturz bringen."""

    async def downstream(scope, receive, send):
        await _asgi_ok(scope, receive, send)

    app = BearerAuthMiddleware(downstream, token_provider=lambda: "tökén-äöü")
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://mcp.test") as client:
        response = await client.get("/mcp", headers={"Authorization": "Bearer falsch"})

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Szenario-Werkzeuge (Support-Faelle)
# ---------------------------------------------------------------------------


async def test_get_order_status_composes_customer_and_tracking(api):
    api.get("/salesOrders").mock(return_value=httpx.Response(200, json=DEMO_SALES_ORDERS_PAGE))
    api.get("/customers/10420").mock(return_value=httpx.Response(200, json=DEMO_CUSTOMER))
    api.get("/deliveryNotes").mock(return_value=httpx.Response(200, json=DEMO_DELIVERY_NOTES_PAGE))

    result = await invoke(
        "get_order_status", {"sales_order_number": "AU-2026-8841"}, OrderStatus
    )

    assert result.order_number == "AU-2026-8841"
    assert result.customer_number == "KD-10420"
    assert result.customer_company == "Musterbau GmbH"
    assert result.payment_status == "bezahlt"
    assert result.delivery_status == "versendet"
    assert result.is_paid is True
    assert result.total_gross == 1489.5
    assert result.currency == "EUR"
    assert result.tracking_id == "00340434161094012345"
    assert len(result.model_dump()) <= 10


async def test_get_order_status_without_match_raises(api):
    api.get("/salesOrders").mock(
        return_value=httpx.Response(200, json={"TotalItems": 0, "Items": []})
    )

    with pytest.raises(ToolError) as excinfo:
        await invoke("get_order_status", {"sales_order_number": "AU-unbekannt"})

    assert "Kein Auftrag" in str(excinfo.value)


async def test_search_customer_orders_returns_customer_orders(api):
    api.get("/customers").mock(return_value=httpx.Response(200, json=DEMO_CUSTOMERS_PAGE))
    api.get("/salesOrders").mock(return_value=httpx.Response(200, json=DEMO_SALES_ORDERS_PAGE))

    result = await invoke(
        "search_customer_orders", {"customer_number": "KD-10420"}, CustomerOrderSearchResult
    )

    assert result.customer_number == "KD-10420"
    assert result.customer_company == "Musterbau GmbH"
    assert result.customer_email == "einkauf@musterbau-gmbh.de"
    assert result.customer_city == "Bückeburg"
    assert result.order_count == 1
    assert result.orders[0].number == "AU-2026-8841"
    assert result.orders[0].payment_status == "bezahlt"


async def test_search_customer_orders_requires_criterion(api):
    with pytest.raises(ToolError):
        await invoke("search_customer_orders", {})


async def test_check_article_stock_sums_available_and_incoming(api):
    api.get("/items").mock(return_value=httpx.Response(200, json=DEMO_ITEMS_PAGE))
    api.get("/stocks").mock(return_value=httpx.Response(200, json=DEMO_STOCKS_PAGE))
    api.get("/warehouses").mock(return_value=httpx.Response(200, json=DEMO_WAREHOUSES_PAGE))

    result = await invoke("check_article_stock", {"sku": "ART-5001"}, ArticleStockResult)

    assert result.item_id == 5001
    assert result.sku == "ART-5001"
    assert result.name == "Industrie-Steuerungsmodul Pro X2"
    assert result.price_net == 249.0
    assert result.available_quantity == 42.0
    assert result.incoming_quantity == 100.0
    assert result.warehouses[0].warehouse_name == "Hauptlager Bückeburg"
    assert len(result.model_dump()) <= 10


async def test_check_article_stock_without_match_raises(api):
    api.get("/items").mock(
        return_value=httpx.Response(200, json={"TotalItems": 0, "Items": []})
    )

    with pytest.raises(ToolError):
        await invoke("check_article_stock", {"sku": "ART-unbekannt"})


async def test_get_shipment_tracking_resolves_carrier(api):
    api.get("/deliveryNotes").mock(return_value=httpx.Response(200, json=DEMO_DELIVERY_NOTES_PAGE))
    api.get("/shippingMethods").mock(
        return_value=httpx.Response(200, json=DEMO_SHIPPING_METHODS)
    )

    result = await invoke(
        "get_shipment_tracking",
        {"sales_order_number": "AU-2026-8841"},
        ShipmentTrackingResult,
    )

    assert result.order_number == "AU-2026-8841"
    assert result.delivery_note_number == "LS-2026-9912"
    assert result.delivery_date == "2026-11-12T07:30:00+01:00"
    assert result.carrier == "DHL Paket"
    assert result.tracking_id == "00340434161094012345"
    assert result.shipped_date == "2026-11-12T08:00:00+01:00"
    assert result.package_count == 1


# ---------------------------------------------------------------------------
# Tool-Registry und Schemata
# ---------------------------------------------------------------------------


async def test_tool_registry_exposes_expected_readonly_tools():
    async with Client(mcp) as client:
        tools = await client.list_tools()

    names = {tool.name for tool in tools}
    assert names == {
        "jtl_wawi_status",
        "jtl_list_customers",
        "jtl_get_customer",
        "jtl_list_items",
        "jtl_get_item",
        "jtl_list_warehouses",
        "jtl_get_item_stock",
        "jtl_list_sales_orders",
        "jtl_get_sales_order",
        "jtl_list_sales_order_line_items",
        "jtl_list_shipments",
        "get_order_status",
        "search_customer_orders",
        "check_article_stock",
        "get_shipment_tracking",
    }
    assert not any(
        keyword in name.lower()
        for name in names
        for keyword in ("create", "update", "delete", "set_", "write", "cancel")
    )


async def test_tool_can_be_called_through_mcp_client(api):
    api.get("/customers").mock(return_value=httpx.Response(200, json=CUSTOMERS_PAGE))

    async with Client(mcp) as client:
        result = await client.call_tool("jtl_list_customers", {"search": "Muster"})

    payload = getattr(result, "structured_content", None) or getattr(
        result, "structuredContent", None
    )
    assert payload is not None
    assert payload["customers"][0]["number"] == "10001"


def test_every_output_model_stays_within_field_budget():
    for name in dir(models):
        candidate = getattr(models, name)
        if (
            isinstance(candidate, type)
            and issubclass(candidate, BaseModel)
            and candidate is not BaseModel
            and candidate.__module__ == models.__name__
        ):
            assert len(candidate.model_fields) <= 10, f"{name} hat zu viele Felder"
