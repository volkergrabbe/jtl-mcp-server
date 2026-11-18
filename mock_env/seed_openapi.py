#!/usr/bin/env python3
"""Erzeugt ``mock_env/jtl_erp_demo.json`` aus der offiziellen JTL-ERP-Spec.

Ausgangspunkt ist ``mock_env/jtl_erp_1.1.json``
(https://developer.jtl-software.com/openapi/erp/1.1.json).

Es werden drei Dinge gemacht:

1. **Basispfad:** Prism ignoriert den ``servers``-Block - er routet immer gegen
   den Pfad-Teil der Spec. Deshalb bekommen alle Pfade das Praefix
   ``/api/eazybusiness/v1`` und der ``servers``-Block zeigt auf
   ``http://127.0.0.1:5883``. Die GET-Aufrufe des ``jtl_client.py``
   (z. B. ``GET /api/eazybusiness/v1/salesOrders``) matchen damit exakt die
   definierten Pfade der Spec.

2. **Cloud-Residuen entfernen:** ``x-tenant-id``/``x-runas`` sind in der
   Cloud-Spec Pflicht-Header, die es in der On-Premise-Wawi nicht gibt, und die
   OAuth2-Security gilt nur fuer die Cloud. Stattdessen wird ein einfaches
   HTTP-Bearer-Schema verwendet - das entspricht der on-prem-Konvention
   (base64-kodierter API-Key als Bearer-Token) und laesst Prism Requests ohne
   Token mit 401 ablehnen.

3. **Deutsche Demodaten:** Fuer die genutzten Endpunkte werden schema-konforme
   ``examples`` hinterlegt. Die Beispiele sind B2B-nah und deutsch, damit das
   LLM in der Demo realistische Antworten sieht statt Platzhaltern wie
   ``"string"`` oder ``0``.

Die JTL-Schemas sind breit und verlangen viele Pflichtfelder
(``additionalProperties: false``). Ein schemagetriebener Generator erzeugt
deshalb zuerst ein vollstaendiges, valides Objekt, das danach mit den
realistischen Demowerten ueberschrieben wird.

Zusaetzlich werden drei reine Demo-Felder ergaenzt (in der Demo-Spec, nicht in
der offiziellen): ``IsPaid`` am Auftrag, ``QuantityIncoming`` am Bestand und
``SalesOrderNumber`` am Lieferschein. Sie bilden ab, was die JTL-Wawi in
aelteren Versionen bzw. in anderen Ansichten ausweist.

Aufruf::

    python3 mock_env/seed_openapi.py
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
SOURCE_SPEC = BASE_DIR / "jtl_erp_1.1.json"
DEMO_SPEC = BASE_DIR / "jtl_erp_demo.json"

# Muss zu JTL_BASE_URL + JTL_API_PATH in start_demo.sh passen.
DEMO_BASE_URL = "http://127.0.0.1:5883"
API_PATH = "/api/eazybusiness/v1"
DEMO_SERVER_URL = f"{DEMO_BASE_URL}{API_PATH}"

CLOUD_ONLY_HEADERS = ("x-tenant-id", "x-runas")

SALES_ORDER_SCHEMA = "JTL.Wawi.Rest.Contracts.Models.V1.SalesOrder.SalesOrder"
CUSTOMER_SCHEMA = "JTL.Wawi.Rest.Contracts.Models.V1.Customer.Customer"
ITEM_SCHEMA = "JTL.Wawi.Rest.Contracts.Models.V1.Item.Item"
STOCK_SCHEMA = "JTL.Wawi.Rest.Contracts.Models.V1.Stock.Stock"
WAREHOUSE_SCHEMA = "JTL.Wawi.Rest.Contracts.Models.V1.Warehouse.Warehouse"
DELIVERY_NOTE_SCHEMA = "JTL.Wawi.Rest.Contracts.Models.V1.DeliveryNote.DeliveryNote"
PACKAGE_SCHEMA = "JTL.Wawi.Rest.Contracts.Models.V1.DeliveryNote.DeliveryNotePackage"
SHIPPING_METHOD_SCHEMA = "JTL.Wawi.Rest.Contracts.Models.V1.ShippingMethod.ShippingMethod"

# --- Standardwerte fuer generierte Pflichtfelder ----------------------------

STRING_DEFAULTS: dict[str, str] = {
    "Name": "Musterbau GmbH",
    "Company": "Musterbau GmbH",
    "Company2": "",
    "FirstName": "Sabine",
    "LastName": "Krüger",
    "Street": "Industriestraße 14",
    "Address2": "",
    "PostalCode": "31675",
    "City": "Bückeburg",
    "State": "Nordrhein-Westfalen",
    "CountryIso": "DE",
    "Iso": "DE",
    "LanguageIso": "de-DE",
    "CurrencyIso": "EUR",
    "CurrencySymbol": "€",
    "EmailAddress": "einkauf@musterbau-gmbh.de",
    "PhoneNumber": "+49 5722 123456",
    "MobilePhoneNumber": "+49 171 1234567",
    "Fax": "",
    "VatID": "DE812345678",
    "FormOfAddress": "Firma",
    "Title": "",
    "Description": "Beispiel aus der JTL-Wawi-Demoumgebung",
    "ShortDescription": "Demoposition",
    "Comment": "",
    "Notice": "",
    "Annotation": "Demodatensatz",
    "SearchTerms": "demo",
    "Taric": "85371000",
    "CountryOfOrigin": "DE",
    "TrackingID": "00340434161094012345",
    "TrackingUrl": "https://www.dhl.de/sendung/00340434161094012345",
    "BatchNumber": "",
    "ShelfLifeExpirationDate": "",
    "StorageLocationName": "A-01-03",
    "Website": "https://musterbau-gmbh.de",
    "TaxIdentificationNumber": "DE812345678",
    "CommercialRegisterNumber": "HRB 123456",
    "EbayUsername": "",
    "InitialContact": "",
    "Birthday": "",
    "Gtin": "4012345678901",
    "ManufacturerNumber": "MFR-5001-X2",
    "ISBN": "",
    "UPC": "",
    "AmazonFnsku": "",
    "OwnIdentifier": "",
    "SalesChannelId": "DEINTERN",
    "Number": "AU-2026-8841",
    "ExternalNumber": "WEB-2026-118841",
    "BillingNumber": "RE-2026-44219",
}

DATE_DEFAULTS = {
    "date": "2026-11-04",
    "date-time": "2026-11-10T09:15:00",
    "time": "09:15:00",
}

NUMBER_DEFAULTS: dict[str, float] = {
    "Quantity": 5.0,
    "QuantityTotal": 0.0,
    "QuantityLockedForShipment": 0.0,
    "QuantityLockedForAvailability": 0.0,
    "QuantityInPickingLists": 0.0,
    "SalesPriceNet": 249.0,
    "SalesPriceGross": 296.31,
    "PurchasePriceNet": 148.5,
    "SuggestedRetailPrice": 299.0,
    "TotalGrossAmount": 1489.5,
    "StillToPay": 0.0,
    "CashDiscount": 0.0,
    "TaxRate": 19.0,
    "Discount": 0.0,
    "Weights": 1.8,
    "ItemWeigth": 0.85,
    "ShippingWeight": 1.1,
    "Length": 12.5,
    "Width": 8.0,
    "Height": 4.5,
    "CreditLimit": 50000,
    "MinimumOrderQuantity": 1,
    "PermissibleOrderQuantity": 0,
    "PaymentTarget": 14,
    "CashDiscountDays": 0,
    "ShippingPriority": 0,
    "ExtraWeight": 0.0,
    "GrossPrice": 5.95,
    "Priority": 0,
    "TotalNetAmount": 1251.68,
}


# --- Spec-Werkzeuge ----------------------------------------------------------


def resolve_ref(spec: Mapping[str, Any], schema: Mapping[str, Any]) -> Mapping[str, Any]:
    """Folgt ``$ref`` (und ``allOf``) bis zum eigentlichen Schema."""

    seen = 0
    while "$ref" in schema and seen < 20:
        seen += 1
        ref = schema["$ref"]
        if not ref.startswith("#/components/schemas/"):
            return schema
        schema = spec["components"]["schemas"][ref.rsplit("/", 1)[-1]]

    if "allOf" in schema:
        merged: dict[str, Any] = {"type": "object", "properties": {}, "required": []}
        for part in schema["allOf"]:
            part = resolve_ref(spec, part)
            merged["properties"].update(part.get("properties", {}))
            merged["required"].extend(part.get("required", []))
        for key, value in schema.items():
            if key != "allOf":
                merged.setdefault(key, value)
        return merged
    return schema


def build_example(spec: Mapping[str, Any], schema: Mapping[str, Any]) -> Any:
    """Erzeugt einen schema-konformen Beispielwert."""

    schema = resolve_ref(spec, schema)

    if "example" in schema:
        return schema["example"]
    if schema.get("enum"):
        return schema["enum"][0]

    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        schema_type = next((t for t in schema_type if t != "null"), "string")

    if schema_type == "object" or "properties" in schema:
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        return {
            name: build_example(spec, prop_schema)
            for name, prop_schema in properties.items()
            if name in required
        }

    if schema_type == "array":
        return [build_example(spec, schema.get("items", {"type": "string"}))]

    if schema_type == "integer":
        return int(NUMBER_DEFAULTS.get(schema.get("title", ""), 1))

    if schema_type == "number":
        return float(NUMBER_DEFAULTS.get(schema.get("title", ""), 1.0))

    if schema_type == "boolean":
        return True

    if schema_type == "string":
        fmt = schema.get("format")
        if fmt in DATE_DEFAULTS:
            return DATE_DEFAULTS[fmt]
        if fmt == "uuid":
            return "00000000-0000-0000-0000-000000000001"
        if fmt == "email":
            return STRING_DEFAULTS["EmailAddress"]
        if fmt in ("uri", "url"):
            return "https://musterbau-gmbh.de"
        if fmt == "byte":
            return "ZGVtby1iYXNlNjQ="
        return STRING_DEFAULTS.get(schema.get("title", ""), "Demowert")

    return None


def set_path(target: dict[str, Any], dotted: str, value: Any) -> None:
    """Setzt einen Wert ueber einen Punktpfad (``"BillingAddress.Company"``)."""

    parts = dotted.split(".")
    cursor = target
    for part in parts[:-1]:
        nxt = cursor.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cursor[part] = nxt
        cursor = nxt
    cursor[parts[-1]] = value


def paged(spec: Mapping[str, Any], schema_ref: str, items: list[Any]) -> dict[str, Any]:
    """Baut das PagedList-Objekt (Items/PageNumber/PageSize/TotalItems)."""

    page = build_example(spec, {"$ref": f"#/components/schemas/{schema_ref}"})
    page["Items"] = items
    page["TotalItems"] = len(items)
    page["PageNumber"] = 1
    page["PageSize"] = 50
    page["TotalPages"] = 1
    page["HasPreviousPage"] = False
    page["HasNextPage"] = False
    page["NextPageNumber"] = 0
    page["PreviousPageNumber"] = 0
    return page


# --- Demodaten ---------------------------------------------------------------


def demo_sales_order(spec: Mapping[str, Any]) -> dict[str, Any]:
    order = build_example(spec, {"$ref": f"#/components/schemas/{SALES_ORDER_SCHEMA}"})
    set_path(order, "Id", 8841)
    set_path(order, "Number", "AU-2026-8841")
    set_path(order, "ExternalNumber", "WEB-2026-118841")
    set_path(order, "BillingNumber", "RE-2026-44219")
    set_path(order, "CustomerId", 10420)
    set_path(order, "CustomerVatID", "DE812345678")
    set_path(order, "MerchantVatID", "DE998877665")
    set_path(order, "SalesOrderDate", "2026-11-10T09:15:00+01:00")
    set_path(order, "IsCancelled", False)
    set_path(order, "IsExternalInvoice", False)
    set_path(order, "LanguageIso", "de-DE")
    set_path(order, "SalesChannelId", "DEINTERN")
    set_path(order, "Comment", "Bitte an die Warenannahme in Hof 2 liefern.")
    set_path(order, "CustomerComment", "Rahmenauftrag Q4/2026")
    set_path(order, "TransactionStatusId", 2)
    set_path(order, "BillingAddress.Company", "Musterbau GmbH")
    set_path(order, "BillingAddress.FirstName", "Sabine")
    set_path(order, "BillingAddress.LastName", "Krüger")
    set_path(order, "BillingAddress.Street", "Industriestraße 14")
    set_path(order, "BillingAddress.PostalCode", "31675")
    set_path(order, "BillingAddress.City", "Bückeburg")
    set_path(order, "BillingAddress.CountryIso", "DE")
    set_path(order, "BillingAddress.EmailAddress", "einkauf@musterbau-gmbh.de")
    set_path(order, "BillingAddress.PhoneNumber", "+49 5722 123456")
    set_path(order, "Shipmentaddress.Company", "Musterbau GmbH")
    set_path(order, "Shipmentaddress.Street", "Industriestraße 14")
    set_path(order, "Shipmentaddress.Address2", "Tor 2, Warenannahme")
    set_path(order, "Shipmentaddress.PostalCode", "31675")
    set_path(order, "Shipmentaddress.City", "Bückeburg")
    set_path(order, "Shipmentaddress.CountryIso", "DE")
    # Bezahlt.
    set_path(order, "SalesOrderPaymentDetails.PaymentStatus", 2)
    set_path(order, "SalesOrderPaymentDetails.PaymentMethodId", 3)
    set_path(order, "SalesOrderPaymentDetails.TotalGrossAmount", 1489.5)
    set_path(order, "SalesOrderPaymentDetails.TotalNetAmount", 1251.68)
    set_path(order, "SalesOrderPaymentDetails.CurrencyIso", "EUR")
    set_path(order, "SalesOrderPaymentDetails.CurrencySymbol", "€")
    set_path(order, "SalesOrderPaymentDetails.DateOfPayment", "2026-11-11T10:00:00")
    set_path(order, "SalesOrderPaymentDetails.StillToPay", 0.0)
    # Versendet.
    set_path(order, "SalesOrderShippingDetail.DeliveryCompleteStatus", 1)
    set_path(order, "SalesOrderShippingDetail.ShippingMethodId", 7)
    set_path(order, "SalesOrderShippingDetail.ShippedDate", "2026-11-12T08:00:00")
    set_path(order, "SalesOrderShippingDetail.DeliveredDate", "2026-11-12T08:00:00")
    # Demo-Feld: entspricht PaymentStatus == 2.
    set_path(order, "IsPaid", True)
    return order


def demo_customer(spec: Mapping[str, Any]) -> dict[str, Any]:
    customer = build_example(spec, {"$ref": f"#/components/schemas/{CUSTOMER_SCHEMA}"})
    set_path(customer, "Id", 10420)
    set_path(customer, "Number", "KD-10420")
    set_path(customer, "CustomerGroupId", 1)
    set_path(customer, "CustomerCategoryId", 1)
    set_path(customer, "InternalCompanyId", 1)
    set_path(customer, "CustomerSince", "2024-03-12T00:00:00+01:00")
    set_path(customer, "LastChange", "2026-11-12T16:40:00+01:00")
    set_path(customer, "LanguageIso", "de-DE")
    set_path(customer, "TaxIdentificationNumber", "DE812345678")
    set_path(customer, "CommercialRegisterNumber", "HRB 123456")
    set_path(customer, "Website", "https://musterbau-gmbh.de")
    set_path(customer, "AccountsReceivableNumber", 10420)
    set_path(customer, "BillingAddress.Company", "Musterbau GmbH")
    set_path(customer, "BillingAddress.Company2", "Stahl- und Fassadenbau")
    set_path(customer, "BillingAddress.FirstName", "Sabine")
    set_path(customer, "BillingAddress.LastName", "Krüger")
    set_path(customer, "BillingAddress.Street", "Industriestraße 14")
    set_path(customer, "BillingAddress.PostalCode", "31675")
    set_path(customer, "BillingAddress.City", "Bückeburg")
    set_path(customer, "BillingAddress.CountryIso", "DE")
    set_path(customer, "BillingAddress.EmailAddress", "einkauf@musterbau-gmbh.de")
    set_path(customer, "BillingAddress.PhoneNumber", "+49 5722 123456")
    set_path(customer, "Shipmentaddress.Company", "Musterbau GmbH")
    set_path(customer, "Shipmentaddress.Street", "Industriestraße 14")
    set_path(customer, "Shipmentaddress.Address2", "Tor 2, Warenannahme")
    set_path(customer, "Shipmentaddress.PostalCode", "31675")
    set_path(customer, "Shipmentaddress.City", "Bückeburg")
    set_path(customer, "Shipmentaddress.CountryIso", "DE")
    set_path(customer, "PaymentSettings.PaymentMethodId", 3)
    set_path(customer, "PaymentSettings.CreditLimit", 50000)
    set_path(customer, "PaymentSettings.PaymentTarget", 14)
    return customer


def demo_item(spec: Mapping[str, Any]) -> dict[str, Any]:
    item = build_example(spec, {"$ref": f"#/components/schemas/{ITEM_SCHEMA}"})
    set_path(item, "Id", 5001)
    set_path(item, "SKU", "ART-5001")
    set_path(item, "Name", "Industrie-Steuerungsmodul Pro X2")
    set_path(item, "Description", "Steuerungsmodul für Schaltschränke, 24 V DC, IP20.")
    set_path(item, "ShortDescription", "Steuerungsmodul Pro X2")
    set_path(item, "IsActive", True)
    set_path(item, "ItemPriceData.SalesPriceNet", 249.0)
    set_path(item, "ItemPriceData.SuggestedRetailPrice", 299.0)
    set_path(item, "ItemPriceData.PurchasePriceNet", 148.5)
    set_path(item, "ItemPriceData.CurrencyIso", "EUR")
    set_path(item, "Identifiers.Gtin", "4012345678901")
    set_path(item, "Identifiers.ManufacturerNumber", "MFR-5001-X2")
    set_path(item, "Weights.ItemWeigth", 0.85)
    set_path(item, "Weights.ShippingWeight", 1.1)
    set_path(item, "Dimensions.Length", 12.5)
    set_path(item, "Dimensions.Width", 8.0)
    set_path(item, "Dimensions.Height", 4.5)
    set_path(item, "Quantities.MinimumOrderQuantity", 1)
    set_path(item, "CountryOfOrigin", "DE")
    set_path(item, "Taric", "85371000")
    set_path(item, "Added", "2024-01-15T08:00:00")
    set_path(item, "Changed", "2026-11-01T08:00:00")
    set_path(item, "Annotation", "Demoartikel")
    return item


def demo_stock_entries(spec: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Hauptlager: 142 Stueck, davon 100 reserviert -> 42 verfuegbar, 100 Zulauf."""

    hauptlager = build_example(spec, {"$ref": f"#/components/schemas/{STOCK_SCHEMA}"})
    set_path(hauptlager, "WarehouseId", 1)
    set_path(hauptlager, "StorageLocationId", 11)
    set_path(hauptlager, "StorageLocationName", "A-01-03")
    set_path(hauptlager, "ItemId", 5001)
    set_path(hauptlager, "QuantityTotal", 142)
    set_path(hauptlager, "QuantityLockedForShipment", 100)
    set_path(hauptlager, "QuantityLockedForAvailability", 0)
    set_path(hauptlager, "QuantityInPickingLists", 0)
    set_path(hauptlager, "BatchNumber", "CH-2026-11")
    set_path(hauptlager, "ShelfLifeExpirationDate", "")
    # Demo-Feld: zugelaufene, noch nicht freigegebene Menge.
    set_path(hauptlager, "QuantityIncoming", 100)
    return [hauptlager]


def demo_warehouses(spec: Mapping[str, Any]) -> list[dict[str, Any]]:
    hauptlager = build_example(spec, {"$ref": f"#/components/schemas/{WAREHOUSE_SCHEMA}"})
    set_path(hauptlager, "Id", 1)
    set_path(hauptlager, "Name", "Hauptlager Bückeburg")
    set_path(hauptlager, "Code", "HL-1")
    set_path(hauptlager, "Description", "Zentrallager für B2B-Versand")
    set_path(hauptlager, "Type.Id", "1")
    set_path(hauptlager, "Type.Name", "Standardlager")
    set_path(hauptlager, "IsActive", True)
    set_path(hauptlager, "Address.Company", "Musterbau GmbH")
    set_path(hauptlager, "Address.Street", "Industriestraße 14")
    set_path(hauptlager, "Address.PostalCode", "31675")
    set_path(hauptlager, "Address.City", "Bückeburg")
    set_path(hauptlager, "Address.CountryIso", "DE")

    zulauf = build_example(spec, {"$ref": f"#/components/schemas/{WAREHOUSE_SCHEMA}"})
    set_path(zulauf, "Id", 2)
    set_path(zulauf, "Name", "Zulauf Wareneingang")
    set_path(zulauf, "Code", "ZUL-1")
    set_path(zulauf, "Description", "Zulauf, noch nicht freigegeben")
    set_path(zulauf, "Type.Id", "2")
    set_path(zulauf, "Type.Name", "Wareneingang")
    set_path(zulauf, "IsActive", True)
    set_path(zulauf, "Address.Company", "Musterbau GmbH")
    set_path(zulauf, "Address.Street", "Industriestraße 14")
    set_path(zulauf, "Address.PostalCode", "31675")
    set_path(zulauf, "Address.City", "Bückeburg")
    set_path(zulauf, "Address.CountryIso", "DE")
    return [hauptlager, zulauf]


def demo_delivery_note(spec: Mapping[str, Any]) -> dict[str, Any]:
    note = build_example(spec, {"$ref": f"#/components/schemas/{DELIVERY_NOTE_SCHEMA}"})
    set_path(note, "Id", 9912)
    set_path(note, "Number", "LS-2026-9912")
    set_path(note, "DeliveryNoteDate", "2026-11-12T07:30:00+01:00")
    # Demo-Feld: zugehoeriger Auftrag.
    set_path(note, "SalesOrderNumber", "AU-2026-8841")
    set_path(note, "SalesOrderId", 8841)
    set_path(note, "CustomerId", 10420)

    package = build_example(spec, {"$ref": f"#/components/schemas/{PACKAGE_SCHEMA}"})
    set_path(package, "Id", 771)
    set_path(package, "PackageDate", "2026-11-12T07:45:00+01:00")
    set_path(package, "ShippedDate", "2026-11-12T08:00:00+01:00")
    set_path(package, "TrackingID", "00340434161094012345")
    set_path(
        package,
        "TrackingUrl",
        "https://www.dhl.de/de/privatkunden/pakete-empfangen/verfolgen.html"
        "?piececode=00340434161094012345",
    )
    set_path(package, "ShippingMethodId", 7)
    set_path(package, "Weights", 1.8)
    set_path(package, "Comment", "2 Kartons")
    note["Packages"] = [package]
    return note


def demo_shipping_methods(spec: Mapping[str, Any]) -> list[dict[str, Any]]:
    methods = []
    for method_id, name, price in ((7, "DHL Paket", 5.95), (4, "DPD Paket", 6.49)):
        method = build_example(spec, {"$ref": f"#/components/schemas/{SHIPPING_METHOD_SCHEMA}"})
        set_path(method, "Id", method_id)
        set_path(method, "Name", name)
        set_path(method, "GrossPrice", price)
        set_path(method, "ExtraWeight", 0.0)
        set_path(method, "Priority", 0)
        set_path(method, "IsAmazonPrime", False)
        methods.append(method)
    return methods


LINE_ITEM_SCHEMA = "JTL.Wawi.Rest.Contracts.Models.V1.SalesOrder.SalesOrderLineItem"


def demo_line_items(spec: Mapping[str, Any]) -> list[dict[str, Any]]:
    line_item = build_example(spec, {"$ref": f"#/components/schemas/{LINE_ITEM_SCHEMA}"})
    set_path(line_item, "Id", 55001)
    set_path(line_item, "SalesOrderId", 8841)
    set_path(line_item, "ItemId", 5001)
    set_path(line_item, "SKU", "ART-5001")
    set_path(line_item, "Name", "Industrie-Steuerungsmodul Pro X2")
    set_path(line_item, "Type", 1)
    set_path(line_item, "Quantity", 5.0)
    set_path(line_item, "QuantityDelivered", 5.0)
    set_path(line_item, "QuantityReturned", 0.0)
    set_path(line_item, "SalesUnit", "Stk")
    set_path(line_item, "SalesPriceNet", 249.0)
    set_path(line_item, "SalesPriceGross", 296.31)
    set_path(line_item, "PurchasePriceNet", 148.5)
    set_path(line_item, "Discount", 0.0)
    set_path(line_item, "TaxRate", 19.0)
    set_path(line_item, "Notice", "")
    return [line_item]


def demo_features(spec: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "Feature": "customer.querycustomers",
            "Version": 1,
            "Release": "Stable",
            "IsUsable": True,
        },
        {
            "Feature": "item.queryitems",
            "Version": 1,
            "Release": "Stable",
            "IsUsable": True,
        },
        {
            "Feature": "stock.querystocksperitem",
            "Version": 1,
            "Release": "Stable",
            "IsUsable": True,
        },
        {
            "Feature": "salesorder.querysalesorders",
            "Version": 1,
            "Release": "Stable",
            "IsUsable": True,
        },
    ]


# --- Spec-Transformation -----------------------------------------------------


def _extend_demo_schemas(spec: dict[str, Any]) -> None:
    """Ergänzt die reinen Demo-Felder in der Demo-Spec."""

    schemas = spec["components"]["schemas"]

    sales_order = schemas.get(SALES_ORDER_SCHEMA)
    if sales_order:
        sales_order.setdefault("properties", {})["IsPaid"] = {
            "type": "boolean",
            "description": "Demo-Feld: entspricht SalesOrderPaymentDetails.PaymentStatus == 2.",
        }

    stock = schemas.get(STOCK_SCHEMA)
    if stock:
        stock.setdefault("properties", {})["QuantityIncoming"] = {
            "type": "number",
            "description": "Demo-Feld: zugelaufene, noch nicht freigegebene Menge.",
        }

    delivery_note = schemas.get(DELIVERY_NOTE_SCHEMA)
    if delivery_note:
        delivery_note.setdefault("properties", {})["SalesOrderNumber"] = {
            "type": "string",
            "description": "Demo-Feld: zugehoeriger Verkaufsauftrag.",
        }


def _prepare_paths_and_auth(spec: dict[str, Any]) -> None:
    """Prism ignoriert den ``servers``-Block, der Basispfad muss in die Pfade.

    Gleichzeitig wird das OAuth2-Schema der Cloud-Spec durch ein HTTP-Bearer-
    Schema ersetzt: der MCP-Client sendet ein base64-kodiertes Bearer-Token
    (on-prem JTL-Wawi-Konvention), das Prism so erwartet.
    """

    # 1) Basispfad vor alle Pfade setzen.
    spec["paths"] = {
        f"{API_PATH}{path}": operation for path, operation in spec.get("paths", {}).items()
    }

    # 2) Bearer-Security statt OAuth2.
    components = spec.setdefault("components", {})
    schemes = components.setdefault("securitySchemes", {})
    schemes.clear()
    schemes["jtl-bearer"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "base64",
        "description": "Base64-kodierter JTL-API-Key (on-prem JTL-Wawi).",
    }
    spec["security"] = [{"jtl-bearer": []}]

    # 3) Operationsebene: OAuth2-Security entfernen, Header-Pflicht lockern.
    for operation in spec["paths"].values():
        for method, details in list(operation.items()):
            if method not in {"get", "post", "put", "patch", "delete", "head", "options"}:
                continue
            details.pop("security", None)
            for parameter in details.get("parameters", []):
                if (
                    parameter.get("in") == "header"
                    and parameter.get("name", "").lower() in CLOUD_ONLY_HEADERS
                ):
                    parameter["required"] = False

    # 4) Server-Block dokumentiert die Basis-URL (Prism nutzt sie nicht).
    spec["servers"] = [
        {
            "url": DEMO_SERVER_URL,
            "description": (
                "Lokaler Prism-Mock. Prism ignoriert Server-URLs; der Basispfad "
                f"{API_PATH} ist deshalb zusätzlich in jedem Pfad enthalten."
            ),
        }
    ]
    spec["x-prism-base-path"] = API_PATH


def _response_content(operation: dict[str, Any]) -> dict[str, Any]:
    """Liefert das application/json-Content-Objekt der 200-Antwort."""

    responses = operation.get("responses", {})
    response = responses.get("200") or responses.get(200)
    if not response:
        raise KeyError("Keine 200-Antwort definiert")
    content = response.get("content", {}).get("application/json")
    if not content:
        raise KeyError("Kein application/json-Content definiert")
    return content


def _inject_examples(spec: dict[str, Any], examples: Mapping[tuple[str, str], Any]) -> list[str]:
    injected: list[str] = []
    for (path, method), value in examples.items():
        full_path = f"{API_PATH}{path}"
        operation = spec.get("paths", {}).get(full_path, {}).get(method)
        if not operation:
            print(f"WARNUNG: {method.upper()} {full_path} fehlt in der Spec", file=sys.stderr)
            continue
        content = _response_content(operation)
        content["examples"] = {
            "jtl-demo": {
                "summary": "Realistische deutsche B2B-Demodaten",
                "value": value,
            }
        }
        injected.append(f"{method.upper()} {path}")
    return injected


def build_demo_spec(source: Path) -> tuple[dict[str, Any], list[str]]:
    spec = copy.deepcopy(json.loads(source.read_text(encoding="utf-8")))
    _prepare_paths_and_auth(spec)
    _extend_demo_schemas(spec)

    order = demo_sales_order(spec)
    customer = demo_customer(spec)
    item = demo_item(spec)
    stocks = demo_stock_entries(spec)
    warehouses = demo_warehouses(spec)
    note = demo_delivery_note(spec)
    methods = demo_shipping_methods(spec)

    examples: dict[tuple[str, str], Any] = {
        ("/feature", "get"): demo_features(spec),
        ("/customers", "get"): paged(
            spec, f"JTL.Wawi.Rest.Contracts.Models.PagedListOf{CUSTOMER_SCHEMA}", [customer]
        ),
        ("/customers/{customerId}", "get"): customer,
        ("/items", "get"): paged(
            spec, f"JTL.Wawi.Rest.Contracts.Models.PagedListOf{ITEM_SCHEMA}", [item]
        ),
        ("/items/{itemId}", "get"): item,
        ("/stocks", "get"): paged(
            spec, f"JTL.Wawi.Rest.Contracts.Models.PagedListOf{STOCK_SCHEMA}", stocks
        ),
        ("/warehouses", "get"): paged(
            spec, f"JTL.Wawi.Rest.Contracts.Models.PagedListOf{WAREHOUSE_SCHEMA}", warehouses
        ),
        ("/salesOrders", "get"): paged(
            spec, f"JTL.Wawi.Rest.Contracts.Models.PagedListOf{SALES_ORDER_SCHEMA}", [order]
        ),
        ("/salesOrders/{salesOrderId}", "get"): order,
        ("/salesOrders/{salesOrderId}/lineitems", "get"): demo_line_items(spec),
        ("/deliveryNotes", "get"): paged(
            spec, f"JTL.Wawi.Rest.Contracts.Models.PagedListOf{DELIVERY_NOTE_SCHEMA}", [note]
        ),
        ("/deliveryNotes/{deliveryNoteId}", "get"): note,
        ("/deliveryNotes/{deliveryNoteId}/packages", "get"): note["Packages"],
        # /shippingMethods liefert laut Spec ein einfaches Array (kein PagedList).
        ("/shippingMethods", "get"): methods,
    }
    injected = _inject_examples(spec, examples)
    return spec, injected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE_SPEC)
    parser.add_argument("--output", type=Path, default=DEMO_SPEC)
    args = parser.parse_args()

    if not args.source.is_file():
        print(f"FEHLER: Quell-Spec nicht gefunden: {args.source}", file=sys.stderr)
        return 1

    spec, injected = build_demo_spec(args.source)
    args.output.write_text(
        json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"Demo-Spec geschrieben: {args.output}")
    print(f"Server-Basis-URL:      {DEMO_SERVER_URL}")
    print(f"Beispiele injiziert:   {len(injected)}")
    for entry in injected:
        print(f"  - {entry}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
