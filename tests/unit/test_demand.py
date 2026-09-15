from decimal import Decimal
from pathlib import Path

from business_coordinator.inventory.demand import (
    calculate_demand_shortages,
    create_demand_aligned_events,
)
from business_coordinator.inventory.reorder import (
    read_csv,
)


def test_shortage_uses_stock_and_open_purchase_orders() -> None:
    inventory = [
        {
            "sku": "SKU-1",
            "quantity": "5",
        },
        {
            "sku": "SKU-OK",
            "quantity": "10",
        },
    ]

    sales = [
        {
            "sku": "SKU-1",
            "quantity": "8",
            "status": "backlog",
        },
        {
            "sku": "SKU-OK",
            "quantity": "4",
            "status": "open",
        },
    ]

    purchases = [
        {
            "sku": "SKU-1",
            "quantity": "1",
            "status": "open",
        },
    ]

    shortages = calculate_demand_shortages(
        inventory,
        sales,
        purchases,
    )

    assert shortages == {
        "SKU-1": Decimal("2"),
    }


def test_completed_sales_are_not_active_demand() -> None:
    inventory = [
        {
            "sku": "SKU-1",
            "quantity": "0",
        }
    ]

    sales = [
        {
            "sku": "SKU-1",
            "quantity": "10",
            "status": "paid",
        },
        {
            "sku": "SKU-1",
            "quantity": "5",
            "status": "shipped",
        },
    ]

    shortages = calculate_demand_shortages(
        inventory,
        sales,
        [],
    )

    assert shortages == {}


def test_shortages_create_simulated_events() -> None:
    events = create_demand_aligned_events(
        {
            "SKU-B": Decimal("3"),
            "SKU-A": Decimal("2"),
        },
        effective_day=Decimal("4"),
    )

    assert len(events) == 2
    assert events[0].payload["sku"] == "SKU-A"
    assert events[0].payload["quantity"] == "2"
    assert events[0].effective_day == Decimal("4")
    assert events[0].state_type == "simulated"

    assert events[1].payload["sku"] == "SKU-B"
    assert events[1].payload["quantity"] == "3"


def test_demo_data_demand_shortages() -> None:
    project_root = Path(__file__).resolve().parents[2]
    data_dir = project_root / "data/demo/raw"

    inventory = read_csv(data_dir / "inventory.csv")
    sales = read_csv(data_dir / "sales_orders.csv")
    purchases = read_csv(data_dir / "purchase_orders.csv")

    shortages = calculate_demand_shortages(
        inventory,
        sales,
        purchases,
    )

    assert shortages == {
        "WB-H098": Decimal("38"),
        "PK-7098": Decimal("5"),
    }
