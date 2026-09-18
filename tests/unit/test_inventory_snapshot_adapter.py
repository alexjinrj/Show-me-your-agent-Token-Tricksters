from datetime import UTC, datetime

import pytest

from core.models import (
    SnapshotBundle,
    SnapshotManifest,
    SnapshotRecord,
)
from tools.inventory.snapshot_adapter import (
    extract_inventory_strategy_rows,
)

SNAPSHOT_ID = "00000000-0000-0000-0000-000000000001"
NOW = datetime(2026, 9, 12, tzinfo=UTC)


def build_snapshot(
    *records: SnapshotRecord,
) -> SnapshotBundle:
    return SnapshotBundle(
        manifest=SnapshotManifest(
            snapshot_id=SNAPSHOT_ID,
            company_id="SG-SME-001",
            as_of_time=NOW,
            created_at=NOW,
            source_event_watermark=None,
            process_definition_versions={
                "order_to_cash": 2,
                "procure_to_pay": 2,
            },
            content_hash="a" * 64,
        ),
        records=records,
    )


def test_extracts_inventory_sales_and_purchase_rows() -> None:
    snapshot = build_snapshot(
        SnapshotRecord(
            record_type="item",
            record_key="SKU-001",
            data={
                "id": "item-001",
                "sku": "SKU-001",
                "name": "Test Item",
                "reorder_point": "5",
            },
        ),
        SnapshotRecord(
            record_type="inventory",
            record_key="inventory-001",
            data={
                "item_id": "item-001",
                "warehouse": "SG-WH-01",
                "quantity": "3",
            },
        ),
        SnapshotRecord(
            record_type="business_object",
            record_key="SO-001",
            data={
                "object_number": "SO-001",
                "object_type": "sales_order",
                "quantity": "8",
                "status": "backlog",
                "details": {
                    "sku": "SKU-001",
                },
            },
        ),
        SnapshotRecord(
            record_type="business_object",
            record_key="PO-001",
            data={
                "object_number": "PO-001",
                "object_type": "purchase_order",
                "quantity": "2",
                "status": "open",
                "details": {
                    "sku": "SKU-001",
                },
            },
        ),
    )

    result = extract_inventory_strategy_rows(snapshot)

    assert result.item_rows == (
        {
            "sku": "SKU-001",
            "name": "Test Item",
            "reorder_point": "5",
        },
    )
    assert result.inventory_rows == (
        {
            "sku": "SKU-001",
            "quantity": "3",
        },
    )
    assert result.sales_rows == (
        {
            "order_number": "SO-001",
            "sku": "SKU-001",
            "quantity": "8",
            "status": "backlog",
        },
    )
    assert result.purchase_rows == (
        {
            "order_number": "PO-001",
            "sku": "SKU-001",
            "quantity": "2",
            "status": "open",
        },
    )


def test_rejects_inventory_with_unknown_item() -> None:
    snapshot = build_snapshot(
        SnapshotRecord(
            record_type="inventory",
            record_key="inventory-unknown",
            data={
                "item_id": "missing-item",
                "warehouse": "SG-WH-01",
                "quantity": "3",
            },
        )
    )

    with pytest.raises(
        ValueError,
        match="references unknown item",
    ):
        extract_inventory_strategy_rows(snapshot)
