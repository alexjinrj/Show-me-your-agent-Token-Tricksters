from __future__ import annotations

from decimal import Decimal

from core.models import ScenarioEvent


def warehouse_capacity_increase(*, workers: int = 1) -> ScenarioEvent:
    if workers <= 0:
        raise ValueError("workers must be greater than zero")
    return ScenarioEvent(
        event_type="resource_capacity_changed",
        effective_day=Decimal("0"),
        payload={"resource_type": "warehouse_staff", "capacity_delta": workers},
    )


def expedited_supplier_delivery(
    purchase_order_number: str | None = None, *, days: int = 5
) -> ScenarioEvent:
    if days <= 0:
        raise ValueError("days must be greater than zero")
    payload: dict[str, object] = {"days_delta": -days, "selection": "next_open_delivery"}
    if purchase_order_number is not None:
        payload["purchase_order_number"] = purchase_order_number
    return ScenarioEvent(
        event_type="supplier_delivery_delayed",
        effective_day=Decimal("0"),
        payload=payload,
    )


def inventory_replenishment(
    sku: str,
    quantity: Decimal,
    *,
    effective_day: Decimal = Decimal("3"),
) -> ScenarioEvent:
    """Create a detached what-if replenishment for one inventory SKU."""
    return ScenarioEvent(
        event_type="inventory_replenishment",
        effective_day=effective_day,
        payload={"sku": sku, "quantity": str(quantity)},
    )
