#!/usr/bin/env python3
"""Build a small, reproducible SGD demo extract from Microsoft's AdventureWorks CSVs."""

from __future__ import annotations

import csv
import hashlib
import json
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

BASE_URL = (
    "https://raw.githubusercontent.com/microsoft/sql-server-samples/master/"
    "samples/databases/adventure-works/oltp-install-script"
)
SOURCE_FILES = (
    "Customer",
    "Vendor",
    "Product",
    "ProductInventory",
    "ProductVendor",
    "SalesOrderHeader",
    "SalesOrderDetail",
    "PurchaseOrderHeader",
    "PurchaseOrderDetail",
)
TARGET_AS_OF = datetime(2026, 9, 12, 23, 59, tzinfo=timezone(timedelta(hours=8)))
SOURCE_WINDOW_END = datetime(2025, 6, 29)
SOURCE_WINDOW_START = SOURCE_WINDOW_END - timedelta(days=89)
DATE_SHIFT = TARGET_AS_OF.replace(tzinfo=None) - SOURCE_WINDOW_END.replace(hour=23, minute=59)


def read_source(cache: Path, name: str) -> tuple[list[list[str]], str]:
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / f"{name}.csv"
    if not path.exists():
        urllib.request.urlretrieve(f"{BASE_URL}/{name}.csv", path)  # noqa: S310
    content = path.read_bytes()
    rows = list(csv.reader(content.decode("utf-8-sig").splitlines(), delimiter="\t"))
    return rows, hashlib.sha256(content).hexdigest()


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def shifted(value: str) -> str:
    result = dt(value) + DATE_SHIFT
    return result.replace(tzinfo=timezone(timedelta(hours=8))).isoformat()


def write_csv(output: Path, name: str, fields: list[str], rows: list[dict[str, object]]) -> None:
    path = output / f"{name}.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def build(output: Path, cache: Path) -> None:
    source: dict[str, list[list[str]]] = {}
    hashes: dict[str, str] = {}
    for name in SOURCE_FILES:
        source[name], hashes[name] = read_source(cache, name)

    product_by_id = {row[0]: row for row in source["Product"]}
    customer_by_id = {row[0]: row for row in source["Customer"]}
    vendor_by_id = {row[0]: row for row in source["Vendor"]}
    sales_header = {row[0]: row for row in source["SalesOrderHeader"]}
    purchase_header = {row[0]: row for row in source["PurchaseOrderHeader"]}

    sales_details_by_order: dict[str, list[list[str]]] = defaultdict(list)
    for row in source["SalesOrderDetail"]:
        sales_details_by_order[row[0]].append(row)
    purchase_details_by_order: dict[str, list[list[str]]] = defaultdict(list)
    for row in source["PurchaseOrderDetail"]:
        purchase_details_by_order[row[0]].append(row)

    sale_frequency = Counter(
        detail[4]
        for order_id, header in sales_header.items()
        if SOURCE_WINDOW_START <= dt(header[2]) <= SOURCE_WINDOW_END
        for detail in sales_details_by_order[order_id]
    )
    purchased_products = {row[4] for row in source["PurchaseOrderDetail"]}
    eligible_products = [
        product_id
        for product_id, _ in sale_frequency.most_common()
        if product_id in purchased_products
        and Decimal(product_by_id[product_id][8]) > 0
        and Decimal(product_by_id[product_id][9]) > 0
    ][:40]
    eligible = set(eligible_products)
    exception_products = set(eligible_products[:3])

    sales_candidates: list[tuple[list[str], list[str]]] = []
    exception_candidates: list[tuple[list[str], list[str]]] = []
    for order_id, header in sales_header.items():
        order_date = dt(header[2])
        if not SOURCE_WINDOW_START <= order_date <= SOURCE_WINDOW_END:
            continue
        details = [row for row in sales_details_by_order[order_id] if row[4] in eligible]
        if not details:
            continue
        pair = (header, details[0])
        sales_candidates.append(pair)
        recent_exception = order_date >= SOURCE_WINDOW_END - timedelta(days=20)
        if details[0][4] in exception_products and recent_exception:
            exception_candidates.append(pair)
    sales_candidates.sort(key=lambda pair: (pair[0][2], int(pair[0][0])))
    exception_candidates.sort(key=lambda pair: (pair[0][2], int(pair[0][0])))
    exception_ids = {pair[0][0] for pair in exception_candidates[-100:]}
    selected_sales = [pair for pair in sales_candidates if pair[0][0] not in exception_ids][-400:]
    selected_sales += [pair for pair in exception_candidates if pair[0][0] in exception_ids]
    selected_sales.sort(key=lambda pair: (pair[0][2], int(pair[0][0])))
    if len(selected_sales) != 500 or len(exception_ids) != 100:
        raise RuntimeError("source no longer provides the expected 500-order deterministic slice")

    purchase_candidates: list[tuple[list[str], list[str]]] = []
    for order_id, header in purchase_header.items():
        order_date = dt(header[6])
        if not SOURCE_WINDOW_START <= order_date <= SOURCE_WINDOW_END:
            continue
        details = [row for row in purchase_details_by_order[order_id] if row[4] in eligible]
        if details:
            purchase_candidates.append((header, details[0]))
    purchase_candidates.sort(key=lambda pair: (pair[0][6], int(pair[0][0])))
    selected_purchases = purchase_candidates[-50:]
    if len(selected_purchases) != 50:
        raise RuntimeError("source no longer provides the expected 50-purchase-order slice")

    selected_customer_ids = sorted({pair[0][10] for pair in selected_sales}, key=int)
    selected_vendor_ids = sorted({pair[0][4] for pair in selected_purchases}, key=int)
    output.mkdir(parents=True, exist_ok=True)

    customer_rows = [
        {
            "customer_number": customer_by_id[value][4],
            "name": f"AdventureWorks Customer {value}",
            "active": "true",
            "business_timestamp": TARGET_AS_OF.isoformat(),
            "data_origin": "derived",
            "source_record_id": value,
        }
        for value in selected_customer_ids
    ]
    write_csv(
        output,
        "customers",
        [
            "customer_number",
            "name",
            "active",
            "business_timestamp",
            "data_origin",
            "source_record_id",
        ],
        customer_rows,
    )

    supplier_rows = [
        {
            "supplier_number": vendor_by_id[value][1],
            "name": vendor_by_id[value][2],
            "active": "true" if vendor_by_id[value][5] == "1" else "false",
            "business_timestamp": TARGET_AS_OF.isoformat(),
            "data_origin": "source",
            "source_record_id": value,
        }
        for value in selected_vendor_ids
    ]
    write_csv(
        output,
        "suppliers",
        [
            "supplier_number",
            "name",
            "active",
            "business_timestamp",
            "data_origin",
            "source_record_id",
        ],
        supplier_rows,
    )

    item_rows = [
        {
            "sku": product_by_id[value][2],
            "name": product_by_id[value][1],
            "standard_cost": product_by_id[value][8],
            "list_price": product_by_id[value][9],
            "reorder_point": product_by_id[value][7],
            "active": "true",
            "business_timestamp": TARGET_AS_OF.isoformat(),
            "data_origin": "source",
            "source_record_id": value,
        }
        for value in eligible_products
    ]
    write_csv(
        output,
        "items",
        [
            "sku",
            "name",
            "standard_cost",
            "list_price",
            "reorder_point",
            "active",
            "business_timestamp",
            "data_origin",
            "source_record_id",
        ],
        item_rows,
    )

    inventory_totals: Counter[str] = Counter()
    inventory_source_ids: dict[str, list[str]] = defaultdict(list)
    for row in source["ProductInventory"]:
        if row[0] in eligible:
            inventory_totals[row[0]] += int(row[4])
            inventory_source_ids[row[0]].append(f"{row[0]}:{row[1]}")
    inventory_rows = []
    for product_id in eligible_products:
        product = product_by_id[product_id]
        quantity = inventory_totals[product_id]
        origin = "derived"
        if product_id in exception_products:
            quantity = max(1, int(Decimal(product[7]) * Decimal("0.35")))
        inventory_rows.append(
            {
                "sku": product[2],
                "warehouse": "SG-WH-01",
                "quantity": quantity,
                "business_timestamp": TARGET_AS_OF.isoformat(),
                "data_origin": origin,
                "source_record_id": "+".join(inventory_source_ids[product_id]),
            }
        )
    write_csv(
        output,
        "inventory",
        ["sku", "warehouse", "quantity", "business_timestamp", "data_origin", "source_record_id"],
        inventory_rows,
    )

    sales_rows = []
    for index, (header, detail) in enumerate(selected_sales):
        status = "backlog" if header[0] in exception_ids else ("paid" if index % 3 else "shipped")
        sales_rows.append(
            {
                "order_number": header[7],
                "customer_number": customer_by_id[header[10]][4],
                "sku": product_by_id[detail[4]][2],
                "quantity": detail[3],
                "unit_price": detail[6],
                "order_date": shifted(header[2]),
                "due_date": shifted(header[3]),
                "status": status,
                "priority": "1" if status == "backlog" else "0",
                "data_origin": "derived",
                "source_record_id": f"{header[0]}:{detail[1]}",
            }
        )
    write_csv(
        output,
        "sales_orders",
        [
            "order_number",
            "customer_number",
            "sku",
            "quantity",
            "unit_price",
            "order_date",
            "due_date",
            "status",
            "priority",
            "data_origin",
            "source_record_id",
        ],
        sales_rows,
    )

    purchase_rows = []
    for index, (header, detail) in enumerate(selected_purchases):
        status = "open" if index >= 40 else "received"
        purchase_rows.append(
            {
                "order_number": f"PO{header[0]}",
                "supplier_number": vendor_by_id[header[4]][1],
                "sku": product_by_id[detail[4]][2],
                "quantity": detail[3],
                "unit_cost": detail[5],
                "order_date": shifted(header[6]),
                "due_date": shifted(detail[2]),
                "status": status,
                "priority": "1" if status == "open" else "0",
                "data_origin": "derived",
                "source_record_id": f"{header[0]}:{detail[1]}",
            }
        )
    write_csv(
        output,
        "purchase_orders",
        [
            "order_number",
            "supplier_number",
            "sku",
            "quantity",
            "unit_cost",
            "order_date",
            "due_date",
            "status",
            "priority",
            "data_origin",
            "source_record_id",
        ],
        purchase_rows,
    )

    resources = [
        ("sales_staff", "order_to_cash", "credit_review", "3"),
        ("warehouse_staff", "order_to_cash", "pick_and_pack", "2"),
        ("finance_staff", "order_to_cash", "invoiced", "2"),
        ("purchasing_staff", "procure_to_pay", "purchase_order_placed", "2"),
        ("warehouse_staff", "procure_to_pay", "goods_received", "2"),
        ("finance_staff", "procure_to_pay", "supplier_invoice_recorded", "2"),
    ]
    write_csv(
        output,
        "resources",
        [
            "resource_type",
            "process_id",
            "node_id",
            "capacity_units",
            "effective_at",
            "data_origin",
            "source_record_id",
        ],
        [
            {
                "resource_type": resource_type,
                "process_id": process_id,
                "node_id": node_id,
                "capacity_units": capacity,
                "effective_at": TARGET_AS_OF.isoformat(),
                "data_origin": "synthetic",
                "source_record_id": f"resource:{index}",
            }
            for index, (resource_type, process_id, node_id, capacity) in enumerate(resources, 1)
        ],
    )

    balances = {
        "CASH": "85000.00",
        "ACCOUNTS_RECEIVABLE": "142000.00",
        "ACCOUNTS_PAYABLE": "97000.00",
        "REVENUE": "610000.00",
        "COST_OF_GOODS_SOLD": "389000.00",
        "INVENTORY": "128000.00",
    }
    write_csv(
        output,
        "opening_balances",
        [
            "account_code",
            "amount",
            "currency",
            "business_timestamp",
            "data_origin",
            "source_record_id",
        ],
        [
            {
                "account_code": code,
                "amount": amount,
                "currency": "SGD",
                "business_timestamp": TARGET_AS_OF.isoformat(),
                "data_origin": "synthetic",
                "source_record_id": f"balance:{code}",
            }
            for code, amount in balances.items()
        ],
    )

    manifest = {
        "dataset": "Microsoft AdventureWorks OLTP install-script CSV files",
        "source_base_url": BASE_URL,
        "license": "MIT",
        "license_url": "https://github.com/microsoft/sql-server-samples/blob/master/license.txt",
        "source_file_sha256": hashes,
        "transform": {
            "script": "scripts/build_demo_data.py",
            "target_company": "SG-SME-001",
            "target_currency": "SGD",
            "target_timezone": "Asia/Singapore (+08:00)",
            "source_window": [
                SOURCE_WINDOW_START.date().isoformat(),
                SOURCE_WINDOW_END.date().isoformat(),
            ],
            "target_as_of": TARGET_AS_OF.isoformat(),
            "data_origin_policy": {
                "source": "values copied without business reinterpretation",
                "derived": "source-linked values rebased, aggregated, renamed, or status-adapted",
                "synthetic": "MVP-only capacity and accounting assumptions",
            },
        },
        "row_counts": {
            "customers": len(customer_rows),
            "suppliers": len(supplier_rows),
            "items": len(item_rows),
            "inventory": len(inventory_rows),
            "sales_orders": len(sales_rows),
            "purchase_orders": len(purchase_rows),
            "resources": len(resources),
            "opening_balances": len(balances),
        },
        "embedded_exception": {
            "affected_skus": [product_by_id[value][2] for value in eligible_products[:3]],
            "backlog_orders": 100,
            "warehouse_staff_capacity": 2,
            "inventory_rule": "35% of the AdventureWorks reorder point for affected SKUs",
        },
    }
    (output / "SOURCE_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    expected = output.parent / "expected"
    expected.mkdir(parents=True, exist_ok=True)
    (expected / "exception.json").write_text(
        json.dumps(manifest["embedded_exception"], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    repository = Path(__file__).resolve().parents[1]
    build(repository / "data/demo/raw", repository / ".cache/adventureworks")
