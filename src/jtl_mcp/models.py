"""Kompakte, token-optimierte Output-Schemas.

Die JTL-Wawi-REST-API liefert sehr breite Objekte mit dutzenden internen
Metafeldern. Für MCP-Consumer werden hier bewusst flache Modelle mit maximal
6-10 Feldern definiert. Die Abbildung von der API-Antwort auf das Modell
passiert in den ``from_api``-Klassenmethoden.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field

# Statuscodes laut OpenAPI-Spec (x-enumNames)
PAYMENT_STATUS: dict[int, str] = {
    0: "unbezahlt",
    1: "teilzahlung",
    2: "bezahlt",
}

DELIVERY_STATUS: dict[int, str] = {
    0: "nicht_versendet",
    1: "versendet",
    2: "versendet_ohne_lieferschein",
}

LINE_ITEM_TYPES: dict[int, str] = {
    0: "leer",
    1: "artikel",
    2: "versand",
    3: "gutschein",
    4: "wertgutschein",
    5: "zahlung",
    6: "versandzuschlag",
    10: "verpackung",
    11: "geschenk",
}


# --- Hilfsfunktionen --------------------------------------------------------


def _first(raw: Mapping[str, Any], *names: str, default: Any = None) -> Any:
    """Liefert den ersten vorhandenen Wert (case-insensitiv als Fallback)."""

    for name in names:
        value = raw.get(name)
        if value is not None:
            return value
    lowered = {key.lower(): value for key, value in raw.items()}
    for name in names:
        value = lowered.get(name.lower())
        if value is not None:
            return value
    return default


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return str(value)


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def _person(raw: Mapping[str, Any]) -> str | None:
    """Baut aus Vor-/Nachname einen Anzeigenamen."""

    first = _text(raw.get("FirstName"))
    last = _text(raw.get("LastName"))
    return " ".join(part for part in (first, last) if part) or None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


# --- Modelle ----------------------------------------------------------------


class Address(BaseModel):
    """Kompakte Anschrift."""

    company: str | None = None
    contact_name: str | None = None
    street: str | None = None
    postal_code: str | None = None
    city: str | None = None
    country: str | None = None

    @classmethod
    def from_api(cls, raw: Any) -> Address | None:
        data = _mapping(raw)
        street = " ".join(
            part for part in (_text(data.get("Street")), _text(data.get("Address2"))) if part
        )
        return cls(
            company=_text(data.get("Company")) or _text(data.get("Company2")),
            contact_name=_person(data),
            street=street or None,
            postal_code=_text(data.get("PostalCode")),
            city=_text(data.get("City")),
            country=_text(data.get("CountryIso")),
        )


class CustomerSummary(BaseModel):
    """Kundenliste - auf 8 Felder reduziert."""

    id: int
    number: str | None = None
    company: str | None = None
    contact_name: str | None = None
    city: str | None = None
    email: str | None = None
    customer_group_id: int | None = None
    customer_since: str | None = None

    @classmethod
    def from_api(cls, raw: Mapping[str, Any]) -> CustomerSummary:
        billing = _mapping(_first(raw, "BillingAddress"))
        return cls(
            id=_int(_first(raw, "Id")) or 0,
            number=_text(_first(raw, "Number")),
            company=_text(billing.get("Company")) or _text(billing.get("Company2")),
            contact_name=_person(billing),
            city=_text(billing.get("City")),
            email=_text(billing.get("EmailAddress")),
            customer_group_id=_int(_first(raw, "CustomerGroupId")),
            customer_since=_text(_first(raw, "CustomerSince")),
        )


class CustomerDetail(BaseModel):
    """Kundendetails - auf 10 Felder reduziert."""

    id: int
    number: str | None = None
    company: str | None = None
    contact_name: str | None = None
    email: str | None = None
    phone: str | None = None
    customer_group_id: int | None = None
    billing_address: Address | None = None
    shipment_address: Address | None = None
    last_change: str | None = None

    @classmethod
    def from_api(cls, raw: Mapping[str, Any]) -> CustomerDetail:
        billing_raw = _first(raw, "BillingAddress")
        shipment_raw = _first(raw, "ShipmentAddress", "Shipmentaddress")
        billing = _mapping(billing_raw)
        return cls(
            id=_int(_first(raw, "Id")) or 0,
            number=_text(_first(raw, "Number")),
            company=_text(billing.get("Company")) or _text(billing.get("Company2")),
            contact_name=_person(billing),
            email=_text(billing.get("EmailAddress")),
            phone=_text(billing.get("PhoneNumber")),
            customer_group_id=_int(_first(raw, "CustomerGroupId")),
            billing_address=Address.from_api(billing_raw),
            shipment_address=Address.from_api(shipment_raw),
            last_change=_text(_first(raw, "LastChange")),
        )


class ItemSummary(BaseModel):
    """Artikelliste - auf 10 Felder reduziert."""

    id: int
    sku: str | None = None
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None
    price_net: float | None = None
    suggested_retail_price: float | None = None
    gtin: str | None = None
    manufacturer_number: str | None = None
    last_change: str | None = None

    @classmethod
    def from_api(cls, raw: Mapping[str, Any]) -> ItemSummary:
        price = _mapping(_first(raw, "ItemPriceData"))
        identifiers = _mapping(_first(raw, "Identifiers"))
        return cls(
            id=_int(_first(raw, "Id")) or 0,
            sku=_text(_first(raw, "SKU")),
            name=_text(_first(raw, "Name")),
            description=_text(_first(raw, "Description")),
            is_active=_first(raw, "IsActive"),
            price_net=_number(price.get("SalesPriceNet")),
            suggested_retail_price=_number(price.get("SuggestedRetailPrice")),
            gtin=_text(identifiers.get("Gtin")),
            manufacturer_number=_text(identifiers.get("ManufacturerNumber")),
            last_change=_text(_first(raw, "Changed")),
        )


class ItemDetail(BaseModel):
    """Artikeldetails - auf 10 Felder reduziert."""

    id: int
    sku: str | None = None
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None
    price_net: float | None = None
    purchase_price_net: float | None = None
    gtin: str | None = None
    item_weight: float | None = None
    shipping_weight: float | None = None

    @classmethod
    def from_api(cls, raw: Mapping[str, Any]) -> ItemDetail:
        price = _mapping(_first(raw, "ItemPriceData"))
        identifiers = _mapping(_first(raw, "Identifiers"))
        weights = _mapping(_first(raw, "Weights"))
        return cls(
            id=_int(_first(raw, "Id")) or 0,
            sku=_text(_first(raw, "SKU")),
            name=_text(_first(raw, "Name")),
            description=_text(_first(raw, "Description")),
            is_active=_first(raw, "IsActive"),
            price_net=_number(price.get("SalesPriceNet")),
            purchase_price_net=_number(price.get("PurchasePriceNet")),
            gtin=_text(identifiers.get("Gtin")),
            item_weight=_number(weights.get("ItemWeigth")),
            shipping_weight=_number(weights.get("ShippingWeight")),
        )


class Warehouse(BaseModel):
    """Lager - auf 6 Felder reduziert."""

    id: int
    name: str | None = None
    code: str | None = None
    type: str | None = None
    description: str | None = None
    is_active: bool | None = None

    @classmethod
    def from_api(cls, raw: Mapping[str, Any]) -> Warehouse:
        warehouse_type = _mapping(_first(raw, "Type"))
        return cls(
            id=_int(_first(raw, "Id")) or 0,
            name=_text(_first(raw, "Name")),
            code=_text(_first(raw, "Code")),
            type=_text(warehouse_type.get("Name")) or _text(warehouse_type.get("Id")),
            description=_text(_first(raw, "Description")),
            is_active=_first(raw, "IsActive"),
        )


class StockEntry(BaseModel):
    """Lagerbestand je Lager - auf 9 Felder reduziert."""

    item_id: int
    warehouse_id: int
    warehouse_name: str | None = None
    storage_location: str | None = None
    quantity_total: float | None = None
    quantity_locked_for_shipment: float | None = None
    quantity_available: float | None = None
    quantity_incoming: float | None = None
    batch_number: str | None = None

    @classmethod
    def from_api(
        cls, raw: Mapping[str, Any], warehouse_names: Mapping[int, str] | None = None
    ) -> StockEntry:
        total = _number(_first(raw, "QuantityTotal"))
        locked = _number(_first(raw, "QuantityLockedForShipment"))
        warehouse_id = _int(_first(raw, "WarehouseId")) or 0
        return cls(
            item_id=_int(_first(raw, "ItemId")) or 0,
            warehouse_id=warehouse_id,
            warehouse_name=(warehouse_names or {}).get(warehouse_id),
            storage_location=_text(_first(raw, "StorageLocationName")),
            quantity_total=total,
            quantity_locked_for_shipment=locked,
            quantity_available=(
                None if total is None or locked is None else round(total - locked, 3)
            ),
            quantity_incoming=_number(_first(raw, "QuantityIncoming")),
            batch_number=_text(_first(raw, "BatchNumber")),
        )


class SalesOrderSummary(BaseModel):
    """Auftragsliste - auf 10 Felder reduziert."""

    id: int
    number: str | None = None
    customer_id: int | None = None
    order_date: str | None = None
    payment_status: str | None = None
    delivery_status: str | None = None
    is_paid: bool | None = None
    total_gross: float | None = None
    currency: str | None = None
    is_cancelled: bool | None = None

    @classmethod
    def from_api(cls, raw: Mapping[str, Any]) -> SalesOrderSummary:
        payment = _mapping(_first(raw, "SalesOrderPaymentDetails"))
        shipping = _mapping(_first(raw, "SalesOrderShippingDetail"))
        payment_status = PAYMENT_STATUS.get(_int(payment.get("PaymentStatus")) or 0)
        is_paid = _first(raw, "IsPaid")
        if is_paid is None:
            is_paid = payment_status == "bezahlt"
        return cls(
            id=_int(_first(raw, "Id")) or 0,
            number=_text(_first(raw, "Number")),
            customer_id=_int(_first(raw, "CustomerId")),
            order_date=_text(_first(raw, "SalesOrderDate")),
            payment_status=payment_status,
            delivery_status=DELIVERY_STATUS.get(_int(shipping.get("DeliveryCompleteStatus")) or 0),
            is_paid=is_paid,
            total_gross=_number(payment.get("TotalGrossAmount")),
            currency=_text(payment.get("CurrencyIso")),
            is_cancelled=_first(raw, "IsCancelled"),
        )


class SalesOrderDetail(BaseModel):
    """Auftragsdetails - auf 10 Felder reduziert."""

    id: int
    number: str | None = None
    customer_id: int | None = None
    order_date: str | None = None
    payment_status: str | None = None
    delivery_status: str | None = None
    total_gross: float | None = None
    currency: str | None = None
    billing_address: Address | None = None
    shipment_address: Address | None = None

    @classmethod
    def from_api(cls, raw: Mapping[str, Any]) -> SalesOrderDetail:
        payment = _mapping(_first(raw, "SalesOrderPaymentDetails"))
        shipping = _mapping(_first(raw, "SalesOrderShippingDetail"))
        return cls(
            id=_int(_first(raw, "Id")) or 0,
            number=_text(_first(raw, "Number")),
            customer_id=_int(_first(raw, "CustomerId")),
            order_date=_text(_first(raw, "SalesOrderDate")),
            payment_status=PAYMENT_STATUS.get(_int(payment.get("PaymentStatus")) or 0),
            delivery_status=DELIVERY_STATUS.get(_int(shipping.get("DeliveryCompleteStatus")) or 0),
            total_gross=_number(payment.get("TotalGrossAmount")),
            currency=_text(payment.get("CurrencyIso")),
            billing_address=Address.from_api(_first(raw, "BillingAddress")),
            shipment_address=Address.from_api(
                _first(raw, "ShipmentAddress", "Shipmentaddress")
            ),
        )


class LineItem(BaseModel):
    """Auftragsposition - auf 10 Felder reduziert."""

    id: int
    sku: str | None = None
    name: str | None = None
    quantity: float | None = None
    quantity_delivered: float | None = None
    price_net: float | None = None
    price_gross: float | None = None
    tax_rate: float | None = None
    discount: float | None = None
    item_type: str | None = None

    @classmethod
    def from_api(cls, raw: Mapping[str, Any]) -> LineItem:
        item_type = _int(_first(raw, "Type"))
        return cls(
            id=_int(_first(raw, "Id")) or 0,
            sku=_text(_first(raw, "SKU")),
            name=_text(_first(raw, "Name")),
            quantity=_number(_first(raw, "Quantity")),
            quantity_delivered=_number(_first(raw, "QuantityDelivered")),
            price_net=_number(_first(raw, "SalesPriceNet")),
            price_gross=_number(_first(raw, "SalesPriceGross")),
            tax_rate=_number(_first(raw, "TaxRate")),
            discount=_number(_first(raw, "Discount")),
            item_type=LINE_ITEM_TYPES.get(item_type) if item_type is not None else None,
        )


class Shipment(BaseModel):
    """Versandstatus je Paket - auf 9 Felder reduziert."""

    delivery_note_id: int
    delivery_note_number: str | None = None
    delivery_date: str | None = None
    package_id: int
    tracking_id: str | None = None
    tracking_url: str | None = None
    shipping_method_id: int | None = None
    shipped_date: str | None = None
    weight: float | None = None

    @classmethod
    def from_api(
        cls, delivery_note: Mapping[str, Any], package: Mapping[str, Any]
    ) -> Shipment:
        return cls(
            delivery_note_id=_int(_first(delivery_note, "Id")) or 0,
            delivery_note_number=_text(_first(delivery_note, "Number")),
            delivery_date=_text(_first(delivery_note, "DeliveryNoteDate")),
            package_id=_int(_first(package, "Id")) or 0,
            tracking_id=_text(_first(package, "TrackingID")),
            tracking_url=_text(_first(package, "TrackingUrl")),
            shipping_method_id=_int(_first(package, "ShippingMethodId")),
            shipped_date=_text(_first(package, "ShippedDate")),
            weight=_number(_first(package, "Weights")),
        )


# --- Ergebnis-Wrapper -------------------------------------------------------


class CustomerListResult(BaseModel):
    """Antwort der Kundenliste."""

    count: int = Field(description="Anzahl der zurückgegebenen Kunden.")
    total_items: int = Field(description="Gesamtzahl der Treffer in JTL-Wawi.")
    customers: list[CustomerSummary] = Field(default_factory=list)


class ItemListResult(BaseModel):
    """Antwort der Artikelliste."""

    count: int = Field(description="Anzahl der zurückgegebenen Artikel.")
    total_items: int = Field(description="Gesamtzahl der Treffer in JTL-Wawi.")
    items: list[ItemSummary] = Field(default_factory=list)


class WarehouseListResult(BaseModel):
    """Antwort der Lagerliste."""

    count: int = Field(description="Anzahl der zurückgegebenen Lager.")
    warehouses: list[Warehouse] = Field(default_factory=list)


class StockListResult(BaseModel):
    """Antwort der Lagerbestandsabfrage."""

    item_id: int = Field(description="Artikel-ID des abgefragten Artikels.")
    count: int = Field(description="Anzahl der Bestandseinträge.")
    stocks: list[StockEntry] = Field(default_factory=list)


class SalesOrderListResult(BaseModel):
    """Antwort der Auftragsliste."""

    count: int = Field(description="Anzahl der zurückgegebenen Aufträge.")
    total_items: int = Field(description="Gesamtzahl der Treffer in JTL-Wawi.")
    sales_orders: list[SalesOrderSummary] = Field(default_factory=list)


class LineItemListResult(BaseModel):
    """Antwort der Auftragspositionen."""

    count: int = Field(description="Anzahl der Positionen.")
    line_items: list[LineItem] = Field(default_factory=list)


class ShipmentListResult(BaseModel):
    """Antwort der Versandstatusabfrage."""

    count: int = Field(description="Anzahl der zurückgegebenen Pakete.")
    shipments: list[Shipment] = Field(default_factory=list)


class StatusResult(BaseModel):
    """Ergebnis der Betriebsstatus-Abfrage."""

    api_base_url: str = Field(description="Basis-URL der JTL-Wawi-API.")
    reachable: bool = Field(description="True, wenn die API erreichbar ist.")
    api_version: str | None = Field(default=None, description="Gemeldete API-Version.")
    feature_count: int | None = Field(
        default=None, description="Anzahl der von der API gemeldeten Features."
    )
    error: str | None = Field(default=None, description="Fehlertext, falls nicht erreichbar.")


class ShippingMethod(BaseModel):
    """Versandart - auf 3 Felder reduziert."""

    id: int
    name: str | None = None
    gross_price: float | None = None

    @classmethod
    def from_api(cls, raw: Mapping[str, Any]) -> ShippingMethod:
        return cls(
            id=_int(_first(raw, "Id")) or 0,
            name=_text(_first(raw, "Name")),
            gross_price=_number(_first(raw, "GrossPrice")),
        )


# --- Szenario-Werkzeuge (Anwendungsfälle statt Datenfelder) ------------------


class OrderStatus(BaseModel):
    """Statusübersicht eines Auftrags - auf 10 Felder reduziert."""

    order_number: str | None = None
    customer_number: str | None = None
    customer_company: str | None = None
    order_date: str | None = None
    payment_status: str | None = None
    delivery_status: str | None = None
    is_paid: bool | None = None
    total_gross: float | None = None
    currency: str | None = None
    tracking_id: str | None = None


class CustomerOrderSearchResult(BaseModel):
    """Kunde mit seinen Aufträgen."""

    customer_number: str | None = None
    customer_company: str | None = None
    customer_email: str | None = None
    customer_city: str | None = None
    order_count: int = 0
    orders: list[SalesOrderSummary] = Field(default_factory=list)


class ArticleStockResult(BaseModel):
    """Artikel mit Bestand - auf 7 Felder reduziert."""

    item_id: int
    sku: str | None = None
    name: str | None = None
    price_net: float | None = None
    available_quantity: float | None = None
    incoming_quantity: float | None = None
    warehouses: list[StockEntry] = Field(default_factory=list)


class ShipmentTrackingResult(BaseModel):
    """Sendungsstatus eines Auftrags - auf 8 Felder reduziert."""

    order_number: str | None = None
    delivery_note_number: str | None = None
    delivery_date: str | None = None
    carrier: str | None = None
    tracking_id: str | None = None
    tracking_url: str | None = None
    shipped_date: str | None = None
    package_count: int = 0
