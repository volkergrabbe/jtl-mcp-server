"""Realistische JTL-Wawi-Payloads für die Unit-Tests.

Die Payloads enthalten bewusst zahlreiche interne Metafelder (Id-Werte,
Zeitstempel, Flag-Strukturen, verschachtelte Preis-/Adressobjekte), damit die
Tests belegen, dass die MCP-Tools diese Felder konsequent entfernen.
"""

from __future__ import annotations

from typing import Any

# --------------------------------------------------------------------------
# Kunden
# --------------------------------------------------------------------------

CUSTOMER_BILLING_ADDRESS: dict[str, Any] = {
    "Id": 1001,
    "Company": "Muster Handels GmbH",
    "Company2": "",
    "FormOfAddress": "Firma",
    "Title": "",
    "FirstName": "Max",
    "LastName": "Mustermann",
    "Street": "Hauptstraße",
    "Address2": "12",
    "PostalCode": "80331",
    "City": "München",
    "State": "Bayern",
    "CountryIso": "DE",
    "VatID": "DE123456789",
    "PhoneNumber": "+49 89 1234567",
    "MobilePhoneNumber": "+49 170 1234567",
    "EmailAddress": "einkauf@muster-handel.de",
    "Fax": "",
}

CUSTOMER_SHIPMENT_ADDRESS: dict[str, Any] = {
    "Id": 1002,
    "Company": "Muster Handels GmbH - Logistikzentrum",
    "Company2": "",
    "FormOfAddress": "Firma",
    "Title": "",
    "FirstName": "",
    "LastName": "",
    "Street": "Lagerstraße",
    "Address2": "45",
    "PostalCode": "85399",
    "City": "Hallbergmoos",
    "State": "Bayern",
    "CountryIso": "DE",
    "VatID": "",
    "PhoneNumber": "+49 89 7654321",
    "MobilePhoneNumber": "",
    "EmailAddress": "wareneingang@muster-handel.de",
    "Fax": "",
}

CUSTOMER_1: dict[str, Any] = {
    "Id": 42,
    "Number": "10001",
    "CustomerGroupId": 3,
    "BillingAddress": CUSTOMER_BILLING_ADDRESS,
    "Shipmentaddress": CUSTOMER_SHIPMENT_ADDRESS,
    "CustomAddress": None,
    "OtherAddresses": {"Billing": [], "Shipping": [], "Ebay": []},
    "PaymentSettings": {
        "PaymentMethodId": 2,
        "Discount": 0,
        "PaymentTarget": 14,
        "CreditLimit": 50000,
        "StopPaymentRequest": False,
    },
    "CustomerSince": "2019-04-17T00:00:00",
    "LastChange": "2026-11-02T08:14:22",
    "LanguageIso": "DE",
    "InternalCompanyId": 1,
    "CustomerCategoryId": 1,
    "TaxIdentificationNumber": "DE123456789",
    "AccountsReceivableNumber": 10001,
    "CommercialRegisterNumber": "HRB 123456",
    "Website": "https://muster-handel.de",
    "InitialContact": "",
    "EbayUsername": "",
    "Birthday": "",
    "IsLocked": False,
    "IsCashRegisterBased": False,
}

CUSTOMER_2: dict[str, Any] = {
    "Id": 43,
    "Number": "10002",
    "CustomerGroupId": 5,
    "BillingAddress": {
        "Id": 1003,
        "Company": "Beispiel GmbH",
        "FirstName": "Erika",
        "LastName": "Mustermann",
        "Street": "Nebenweg",
        "Address2": "3",
        "PostalCode": "10115",
        "City": "Berlin",
        "CountryIso": "DE",
        "EmailAddress": "kunde@example.de",
        "PhoneNumber": "+49 30 1112223",
    },
    "Shipmentaddress": CUSTOMER_SHIPMENT_ADDRESS,
    "CustomerSince": "2023-11-30T00:00:00",
    "LastChange": "2026-10-21T16:02:11",
    "LanguageIso": "DE",
    "CustomerCategoryId": 1,
    "IsLocked": False,
}

CUSTOMERS_PAGE: dict[str, Any] = {
    "TotalItems": 2,
    "PageNumber": 1,
    "PageSize": 50,
    "Items": [CUSTOMER_1, CUSTOMER_2],
    "TotalPages": 1,
    "HasPreviousPage": False,
    "HasNextPage": False,
    "NextPageNumber": 0,
    "PreviousPageNumber": 0,
}

# --------------------------------------------------------------------------
# Artikel
# --------------------------------------------------------------------------

ITEM_1: dict[str, Any] = {
    "Id": 501,
    "SKU": "ART-1001",
    "ManufacturerId": 9,
    "ResponsiblePersonId": 3,
    "IsActive": True,
    "Categories": [12, 34],
    "Name": "Industrieschraube M8x40",
    "Description": "Verzinkte Industrieschraube, Güte 8.8",
    "ShortDescription": "Schraube M8x40",
    "Identifiers": {
        "Gtin": "4001234567890",
        "ManufacturerNumber": "MAN-0812",
        "ISBN": "",
        "UPC": "",
        "AmazonFnsku": "",
        "Asins": [],
        "OwnIdentifier": "",
    },
    "Components": [],
    "ChildItems": [],
    "ParentItemId": 0,
    "ItemPriceData": {
        "SalesPriceNet": 0.35,
        "SuggestedRetailPrice": 0.99,
        "PurchasePriceNet": 0.12,
        "EbayPrice": 0.0,
        "AmazonPrice": 0.0,
    },
    "ActiveSalesChannels": ["DEINTERN"],
    "SortNumber": 1000,
    "Annotation": "Standardartikel",
    "Added": "2021-06-01T10:00:00",
    "Changed": "2026-09-18T07:45:00",
    "ReleasedOnDate": "2021-06-01T00:00:00",
    "StorageOptions": {"IsSerialNumbered": False, "IsBatchNumbered": False},
    "CountryOfOrigin": "DE",
    "ConditionId": 1,
    "ShippingClassId": 2,
    "ProductGroupId": 7,
    "TaxClassId": 1,
    "Dimensions": {"Length": 4.0, "Width": 0.8, "Height": 0.8},
    "Weights": {"ItemWeigth": 0.021, "ShippingWeight": 0.025},
    "AllowNegativeStock": False,
    "Quantities": {
        "MinimumOrderQuantity": 1,
        "MinimumPurchaseQuantityForCustomerGroup": [],
        "PermissibleOrderQuantity": 0,
    },
    "DangerousGoods": {},
    "Taric": "73181580",
    "SearchTerms": "schraube",
    "PriceListActive": True,
    "IgnoreDiscounts": False,
    "AvailabilityId": 1,
}

ITEM_2: dict[str, Any] = {
    "Id": 502,
    "SKU": "ART-1002",
    "Name": "Dichtung EPDM 20mm",
    "Description": "Schwarze EPDM-Dichtung, 20 mm",
    "IsActive": False,
    "ItemPriceData": {
        "SalesPriceNet": 1.25,
        "SuggestedRetailPrice": 2.49,
        "PurchasePriceNet": 0.4,
    },
    "Identifiers": {"Gtin": "4001234567891", "ManufacturerNumber": "MAN-0820"},
    "Changed": "2026-08-01T12:00:00",
}

ITEMS_PAGE: dict[str, Any] = {
    "TotalItems": 2,
    "PageNumber": 1,
    "PageSize": 50,
    "Items": [ITEM_1, ITEM_2],
    "TotalPages": 1,
    "HasPreviousPage": False,
    "HasNextPage": False,
}

# --------------------------------------------------------------------------
# Lager und Bestand
# --------------------------------------------------------------------------

WAREHOUSES_PAGE: dict[str, Any] = {
    "TotalItems": 2,
    "PageNumber": 1,
    "PageSize": 50,
    "Items": [
        {
            "Id": 1,
            "Name": "Hauptlager",
            "Address": {
                "Id": 1,
                "Company": "Zentrallager GmbH",
                "Street": "Lagerweg",
                "Address2": "1",
                "PostalCode": "85399",
                "City": "Hallbergmoos",
                "CountryIso": "DE",
            },
            "Code": "HL",
            "Type": {"Id": "1", "Name": "Standardlager", "Description": "", "Scope": ["Fulfillment"]},
            "Description": "Zentrallager Nord",
            "Priority": 1,
            "CompanyId": 1,
            "LockForShipment": True,
            "LockForAvailability": True,
            "IsActive": True,
        },
        {
            "Id": 2,
            "Name": "Außenlager Süd",
            "Address": None,
            "Code": "ALS",
            "Type": {"Id": "2", "Name": "Außenlager", "Description": "", "Scope": []},
            "Description": "Auslieferung Süd",
            "Priority": 2,
            "CompanyId": 1,
            "LockForShipment": False,
            "LockForAvailability": False,
            "IsActive": True,
        },
    ],
    "TotalPages": 1,
}

STOCKS_PAGE: dict[str, Any] = {
    "TotalItems": 2,
    "PageNumber": 1,
    "PageSize": 50,
    "Items": [
        {
            "WarehouseId": 1,
            "StorageLocationId": 11,
            "StorageLocationName": "Regal A-01",
            "ItemId": 501,
            "ShelfLifeExpirationDate": "",
            "BatchNumber": "",
            "QuantityTotal": 1200,
            "QuantityLockedForShipment": 200,
            "QuantityLockedForAvailability": 0,
            "QuantityInPickingLists": 50,
        },
        {
            "WarehouseId": 2,
            "StorageLocationId": 21,
            "StorageLocationName": "Regal B-07",
            "ItemId": 501,
            "ShelfLifeExpirationDate": "",
            "BatchNumber": "CHG-2026-11",
            "QuantityTotal": 80,
            "QuantityLockedForShipment": 10,
            "QuantityLockedForAvailability": 0,
            "QuantityInPickingLists": 0,
        },
    ],
    "TotalPages": 1,
}

# --------------------------------------------------------------------------
# Auftraege
# --------------------------------------------------------------------------

SALES_ORDER_1: dict[str, Any] = {
    "Id": 9001,
    "Number": "2026-100234",
    "ExternalNumber": "SHOP-4711",
    "BillingNumber": "2026-100234",
    "CompanyId": 1,
    "DepartureCountry": {"Id": 1, "Name": "Deutschland", "Iso": "DE"},
    "CustomerId": 42,
    "CustomerVatID": "DE123456789",
    "MerchantVatID": "DE987654321",
    "BillingAddress": CUSTOMER_BILLING_ADDRESS,
    "Shipmentaddress": CUSTOMER_SHIPMENT_ADDRESS,
    "SalesOrderDate": "2026-11-04T09:12:00",
    "SalesOrderPaymentDetails": {
        "PaymentMethodId": 2,
        "PaymentStatus": 2,
        "TotalGrossAmount": 476.28,
        "CurrencyIso": "EUR",
        "CurrencyFactor": 1.0,
        "DateOfPayment": "2026-11-05T10:00:00",
        "StillToPay": 0.0,
        "PaymentTarget": 14,
        "CashDiscount": 0.0,
        "CashDiscountDays": 0,
    },
    "SalesOrderShippingDetail": {
        "ShippingMethodId": 3,
        "DeliveryCompleteStatus": 1,
        "ShippingPriority": 0,
        "ShippingDate": "2026-11-05T00:00:00",
        "EstimatedDeliveryDate": "2026-11-06T00:00:00",
        "DeliveredDate": "2026-11-05T18:00:00",
        "OnHoldReasonId": 0,
        "ExtraWeight": 0.0,
    },
    "ColorcodeId": 0,
    "IsExternalInvoice": False,
    "Comment": "",
    "CustomerComment": "Bitte vor 12 Uhr liefern",
    "IsCancelled": False,
    "LanguageIso": "DE",
    "CancellationDetails": None,
    "SalesChannelId": "DEINTERN",
    "UserCreatedId": 3,
    "UserId": 3,
    "TransactionStatusId": 1,
}

SALES_ORDER_2: dict[str, Any] = {
    "Id": 9002,
    "Number": "2026-100235",
    "ExternalNumber": "",
    "BillingNumber": "2026-100235",
    "CustomerId": 43,
    "BillingAddress": CUSTOMER_2["BillingAddress"],
    "Shipmentaddress": CUSTOMER_2["BillingAddress"],
    "SalesOrderDate": "2026-11-10T14:44:00",
    "SalesOrderPaymentDetails": {
        "PaymentMethodId": 1,
        "PaymentStatus": 0,
        "TotalGrossAmount": 119.0,
        "CurrencyIso": "EUR",
    },
    "SalesOrderShippingDetail": {
        "ShippingMethodId": 1,
        "DeliveryCompleteStatus": 0,
    },
    "IsCancelled": True,
    "LanguageIso": "DE",
    "SalesChannelId": "DEINTERN",
}

SALES_ORDERS_PAGE: dict[str, Any] = {
    "TotalItems": 2,
    "PageNumber": 1,
    "PageSize": 50,
    "Items": [SALES_ORDER_1, SALES_ORDER_2],
    "TotalPages": 1,
    "HasPreviousPage": False,
    "HasNextPage": False,
}

SALES_ORDER_LINE_ITEMS: list[dict[str, Any]] = [
    {
        "Id": 70001,
        "SalesOrderId": 9001,
        "ItemId": 501,
        "Name": "Industrieschraube M8x40",
        "SKU": "ART-1001",
        "Type": 1,
        "Quantity": 1000,
        "QuantityDelivered": 1000,
        "QuantityReturned": 0,
        "SalesUnit": "Stk",
        "SalesPriceNet": 0.35,
        "SalesPriceGross": 0.42,
        "Discount": 0.0,
        "PurchasePriceNet": 0.12,
        "TaxRate": 19.0,
        "Notice": "",
    },
    {
        "Id": 70002,
        "SalesOrderId": 9001,
        "ItemId": 0,
        "Name": "Versandkosten",
        "SKU": "",
        "Type": 2,
        "Quantity": 1,
        "QuantityDelivered": 1,
        "QuantityReturned": 0,
        "SalesUnit": "Stk",
        "SalesPriceNet": 5.0,
        "SalesPriceGross": 5.95,
        "Discount": 0.0,
        "PurchasePriceNet": 0.0,
        "TaxRate": 19.0,
        "Notice": "",
    },
]

# --------------------------------------------------------------------------
# Versand / Lieferscheine
# --------------------------------------------------------------------------

DELIVERY_NOTES_PAGE: dict[str, Any] = {
    "TotalItems": 1,
    "PageNumber": 1,
    "PageSize": 25,
    "Items": [
        {
            "Id": 3001,
            "Number": "LS-2026-0042",
            "DeliveryNoteDate": "2026-11-05T17:30:00",
            "Packages": [
                {
                    "Id": 8001,
                    "PackageDate": "2026-11-05T17:35:00",
                    "TrackingID": "00340434161234567890",
                    "Weights": 12.5,
                    "ShippingMethodId": 3,
                    "ShippedDate": "2026-11-05T18:00:00",
                    "TrackingUrl": "https://www.dhl.de/sendung/00340434161234567890",
                    "Comment": "",
                }
            ],
        }
    ],
    "TotalPages": 1,
}

# --------------------------------------------------------------------------
# Feature-Liste (GET /feature)
# --------------------------------------------------------------------------

FEATURES: list[dict[str, Any]] = [
    {"Feature": "customer.querycustomers", "Version": 1, "Release": "Stable", "IsUsable": True},
    {"Feature": "salesorder.querysalesorders", "Version": 1, "Release": "Stable", "IsUsable": True},
    {"Feature": "stock.querystocksperitem", "Version": 1, "Release": "Stable", "IsUsable": True},
]

# --------------------------------------------------------------------------
# Fehlerantworten
# --------------------------------------------------------------------------

ERROR_UNAUTHORIZED: dict[str, Any] = {
    "title": "Unauthorized",
    "status": 401,
    "detail": "Der API-Key ist ungültig oder abgelaufen.",
}

ERROR_NOT_FOUND: dict[str, Any] = {
    "title": "Not Found",
    "status": 404,
    "detail": "Datensatz nicht gefunden.",
}

# --------------------------------------------------------------------------
# Demodaten (identisch zu mock_env/jtl_erp_demo.json)
#
# Werden von den Unit-Tests der Szenario-Werkzeuge und - als Erwartungswerte -
# vom Prism-E2E-Test verwendet.
# --------------------------------------------------------------------------

DEMO_CUSTOMER: dict[str, Any] = {
    "Id": 10420,
    "Number": "KD-10420",
    "CustomerGroupId": 1,
    "CustomerSince": "2024-03-12T00:00:00+01:00",
    "LastChange": "2026-11-12T16:40:00+01:00",
    "BillingAddress": {
        "Id": 1,
        "Company": "Musterbau GmbH",
        "Company2": "Stahl- und Fassadenbau",
        "FirstName": "Sabine",
        "LastName": "Krüger",
        "Street": "Industriestraße 14",
        "Address2": "",
        "PostalCode": "31675",
        "City": "Bückeburg",
        "State": "Nordrhein-Westfalen",
        "CountryIso": "DE",
        "EmailAddress": "einkauf@musterbau-gmbh.de",
        "PhoneNumber": "+49 5722 123456",
    },
    "Shipmentaddress": {
        "Id": 2,
        "Company": "Musterbau GmbH",
        "FirstName": "Sabine",
        "LastName": "Krüger",
        "Street": "Industriestraße 14",
        "Address2": "Tor 2, Warenannahme",
        "PostalCode": "31675",
        "City": "Bückeburg",
        "CountryIso": "DE",
    },
}

DEMO_SALES_ORDER: dict[str, Any] = {
    "Id": 8841,
    "Number": "AU-2026-8841",
    "ExternalNumber": "WEB-2026-118841",
    "BillingNumber": "RE-2026-44219",
    "CustomerId": 10420,
    "CustomerVatID": "DE812345678",
    "SalesOrderDate": "2026-11-10T09:15:00+01:00",
    "IsCancelled": False,
    "IsExternalInvoice": False,
    "LanguageIso": "de-DE",
    "IsPaid": True,
    "BillingAddress": DEMO_CUSTOMER["BillingAddress"],
    "Shipmentaddress": DEMO_CUSTOMER["Shipmentaddress"],
    "SalesOrderPaymentDetails": {
        "PaymentStatus": 2,
        "PaymentMethodId": 3,
        "TotalGrossAmount": 1489.50,
        "TotalNetAmount": 1251.68,
        "CurrencyIso": "EUR",
        "CurrencySymbol": "€",
    },
    "SalesOrderShippingDetail": {
        "DeliveryCompleteStatus": 1,
        "ShippingMethodId": 7,
        "DeliveredDate": "2026-11-12T08:00:00+01:00",
    },
}

DEMO_ITEM: dict[str, Any] = {
    "Id": 5001,
    "SKU": "ART-5001",
    "Name": "Industrie-Steuerungsmodul Pro X2",
    "Description": "Steuerungsmodul für Schaltschränke, 24 V DC, IP20.",
    "IsActive": True,
    "Changed": "2026-11-01T08:00:00+01:00",
    "ItemPriceData": {
        "SalesPriceNet": 249.00,
        "SuggestedRetailPrice": 299.00,
        "PurchasePriceNet": 148.50,
        "CurrencyIso": "EUR",
    },
    "Identifiers": {"Gtin": "4012345678901", "ManufacturerNumber": "MFR-5001-X2"},
    "Weights": {"ItemWeigth": 0.85, "ShippingWeight": 1.10},
}

DEMO_STOCK: dict[str, Any] = {
    "ItemId": 5001,
    "WarehouseId": 1,
    "StorageLocationId": 11,
    "StorageLocationName": "A-01-03",
    "QuantityTotal": 142,
    "QuantityLockedForShipment": 100,
    "QuantityLockedForAvailability": 0,
    "QuantityInPickingLists": 0,
    "QuantityIncoming": 100,
    "BatchNumber": "CH-2026-11",
}

DEMO_WAREHOUSE: dict[str, Any] = {
    "Id": 1,
    "Name": "Hauptlager Bückeburg",
    "Code": "HL-1",
    "Type": {"Id": "1", "Name": "Standardlager"},
    "Description": "Zentrallager für B2B-Versand",
    "IsActive": True,
}

DEMO_PACKAGE: dict[str, Any] = {
    "Id": 771,
    "PackageDate": "2026-11-12T07:45:00+01:00",
    "TrackingID": "00340434161094012345",
    "TrackingUrl": "https://www.dhl.de/sendung/00340434161094012345",
    "ShippingMethodId": 7,
    "ShippedDate": "2026-11-12T08:00:00+01:00",
    "Weights": 1.8,
    "Comment": "2 Kartons",
}

DEMO_DELIVERY_NOTE: dict[str, Any] = {
    "Id": 9912,
    "Number": "LS-2026-9912",
    "DeliveryNoteDate": "2026-11-12T07:30:00+01:00",
    "SalesOrderNumber": "AU-2026-8841",
    "SalesOrderId": 8841,
    "CustomerId": 10420,
    "Packages": [DEMO_PACKAGE],
}

DEMO_SHIPPING_METHODS: list[dict[str, Any]] = [
    {"Id": 7, "Name": "DHL Paket", "GrossPrice": 5.95, "ExtraWeight": 0.0, "Priority": 0},
    {"Id": 4, "Name": "DPD Paket", "GrossPrice": 6.49, "ExtraWeight": 0.0, "Priority": 0},
]


def _demo_page(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Baut eine PagedList-Antwort wie in der JTL-Spec."""

    return {
        "TotalItems": len(items),
        "PageNumber": 1,
        "PageSize": 50,
        "TotalPages": 1,
        "HasPreviousPage": False,
        "HasNextPage": False,
        "Items": items,
    }


DEMO_CUSTOMERS_PAGE = _demo_page([DEMO_CUSTOMER])
DEMO_SALES_ORDERS_PAGE = _demo_page([DEMO_SALES_ORDER])
DEMO_ITEMS_PAGE = _demo_page([DEMO_ITEM])
DEMO_STOCKS_PAGE = _demo_page([DEMO_STOCK])
DEMO_WAREHOUSES_PAGE = _demo_page([DEMO_WAREHOUSE])
DEMO_DELIVERY_NOTES_PAGE = _demo_page([DEMO_DELIVERY_NOTE])
