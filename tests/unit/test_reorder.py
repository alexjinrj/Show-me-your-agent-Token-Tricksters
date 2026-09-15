from pathlib import Path

from business_coordinator.inventory.reorder import (
    build_reorder_recommendations,
    read_csv,
)


def test_reorder_calculation() -> None:
    items = [
        {
            "sku": "SKU-LOW",
            "name": "Low Stock Item",
            "reorder_point": "3",
        },
        {
            "sku": "SKU-ZERO",
            "name": "Zero Stock Item",
            "reorder_point": "3",
        },
        {
            "sku": "SKU-OK",
            "name": "Healthy Stock Item",
            "reorder_point": "3",
        },
    ]

    inventory = [
        {
            "sku": "SKU-LOW",
            "quantity": "1",
        },
        {
            "sku": "SKU-ZERO",
            "quantity": "0",
        },
        {
            "sku": "SKU-OK",
            "quantity": "10",
        },
    ]

    results = build_reorder_recommendations(
        items,
        inventory,
    )

    by_sku = {row["sku"]: row for row in results}

    assert by_sku["SKU-LOW"]["needs_reorder"] == "true"
    assert by_sku["SKU-LOW"]["risk_level"] == "high"
    assert by_sku["SKU-LOW"]["recommended_quantity"] == "5"

    assert by_sku["SKU-ZERO"]["risk_level"] == "critical"
    assert by_sku["SKU-ZERO"]["recommended_quantity"] == "6"

    assert by_sku["SKU-OK"]["needs_reorder"] == "false"
    assert by_sku["SKU-OK"]["risk_level"] == "low"
    assert by_sku["SKU-OK"]["recommended_quantity"] == "0"


def test_demo_data_has_expected_reorder_skus() -> None:
    project_root = Path(__file__).resolve().parents[2]
    data_dir = project_root / "data/demo/raw"

    items = read_csv(data_dir / "items.csv")
    inventory = read_csv(data_dir / "inventory.csv")

    results = build_reorder_recommendations(
        items,
        inventory,
    )

    reorder_skus = {row["sku"] for row in results if row["needs_reorder"] == "true"}

    assert reorder_skus == {
        "WB-H098",
        "PK-7098",
        "TT-M928",
        "GL-H102-M",
        "RA-H123",
        "SJ-0194-M",
    }
