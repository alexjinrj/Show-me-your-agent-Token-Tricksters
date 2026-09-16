from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from core.models import SnapshotBundle


class InventoryStrategyRows(BaseModel):
    """Inventory-related rows extracted from one immutable snapshot."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    item_rows: tuple[dict[str, str], ...]
    inventory_rows: tuple[dict[str, str], ...]
    sales_rows: tuple[dict[str, str], ...]
    purchase_rows: tuple[dict[str, str], ...]


def required_text(
    data: dict[str, Any],
    field: str,
    *,
    record_type: str,
    record_key: str,
) -> str:
    """Read one required snapshot value as non-empty text."""

    value = data.get(field)

    if value is None or str(value).strip() == "":
        raise ValueError(f"{record_type} record {record_key} is missing required field: {field}")

    return str(value)


def extract_inventory_strategy_rows(
    snapshot: SnapshotBundle,
) -> InventoryStrategyRows:
    """Extract inventory strategy inputs from an immutable snapshot."""

    item_rows: list[dict[str, str]] = []
    inventory_rows: list[dict[str, str]] = []
    sales_rows: list[dict[str, str]] = []
    purchase_rows: list[dict[str, str]] = []

    sku_by_item_id: dict[str, str] = {}

    for record in snapshot.records:
        if record.record_type != "item":
            continue

        item_id = required_text(
            record.data,
            "id",
            record_type=record.record_type,
            record_key=record.record_key,
        )
        sku = required_text(
            record.data,
            "sku",
            record_type=record.record_type,
            record_key=record.record_key,
        )

        sku_by_item_id[item_id] = sku

        item_rows.append(
            {
                "sku": sku,
                "name": required_text(
                    record.data,
                    "name",
                    record_type=record.record_type,
                    record_key=record.record_key,
                ),
                "reorder_point": required_text(
                    record.data,
                    "reorder_point",
                    record_type=record.record_type,
                    record_key=record.record_key,
                ),
            }
        )

    for record in snapshot.records:
        if record.record_type == "inventory":
            item_id = required_text(
                record.data,
                "item_id",
                record_type=record.record_type,
                record_key=record.record_key,
            )

            try:
                sku = sku_by_item_id[item_id]
            except KeyError as exc:
                raise ValueError(
                    f"inventory record {record.record_key} references unknown item: {item_id}"
                ) from exc

            inventory_rows.append(
                {
                    "sku": sku,
                    "quantity": required_text(
                        record.data,
                        "quantity",
                        record_type=record.record_type,
                        record_key=record.record_key,
                    ),
                }
            )

        if record.record_type != "business_object":
            continue

        object_type = required_text(
            record.data,
            "object_type",
            record_type=record.record_type,
            record_key=record.record_key,
        )

        if object_type not in {
            "sales_order",
            "purchase_order",
        }:
            continue

        details = record.data.get("details")

        if not isinstance(details, dict):
            raise ValueError(f"business_object record {record.record_key} is missing order details")

        order_row = {
            "order_number": required_text(
                record.data,
                "object_number",
                record_type=record.record_type,
                record_key=record.record_key,
            ),
            "sku": required_text(
                details,
                "sku",
                record_type=record.record_type,
                record_key=record.record_key,
            ),
            "quantity": required_text(
                record.data,
                "quantity",
                record_type=record.record_type,
                record_key=record.record_key,
            ),
            "status": required_text(
                record.data,
                "status",
                record_type=record.record_type,
                record_key=record.record_key,
            ),
        }

        if object_type == "sales_order":
            sales_rows.append(order_row)
        else:
            purchase_rows.append(order_row)

    item_rows.sort(key=lambda row: row["sku"])
    inventory_rows.sort(key=lambda row: row["sku"])
    sales_rows.sort(
        key=lambda row: (
            row["sku"],
            row["order_number"],
        )
    )
    purchase_rows.sort(
        key=lambda row: (
            row["sku"],
            row["order_number"],
        )
    )

    return InventoryStrategyRows(
        item_rows=tuple(item_rows),
        inventory_rows=tuple(inventory_rows),
        sales_rows=tuple(sales_rows),
        purchase_rows=tuple(purchase_rows),
    )
