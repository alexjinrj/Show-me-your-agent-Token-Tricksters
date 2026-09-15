from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from core.models import (
    ScenarioEvent,
)

ACTIVE_SALES_STATUSES = {
    "open",
    "backlog",
}


def calculate_demand_shortages(
    inventory_rows: list[dict[str, str]],
    sales_rows: list[dict[str, str]],
    purchase_rows: list[dict[str, str]],
) -> dict[str, Decimal]:
    current_stock: defaultdict[str, Decimal] = defaultdict(Decimal)
    backlog_demand: defaultdict[str, Decimal] = defaultdict(Decimal)
    incoming_supply: defaultdict[str, Decimal] = defaultdict(Decimal)

    for row in inventory_rows:
        current_stock[row["sku"]] += Decimal(row["quantity"])

    for row in sales_rows:
        if row["status"] in ACTIVE_SALES_STATUSES:
            backlog_demand[row["sku"]] += Decimal(row["quantity"])

    for row in purchase_rows:
        if row["status"] == "open":
            incoming_supply[row["sku"]] += Decimal(row["quantity"])

    shortages: dict[str, Decimal] = {}

    for sku, demand in backlog_demand.items():
        available_quantity = current_stock[sku] + incoming_supply[sku]

        shortage = max(
            Decimal("0"),
            demand - available_quantity,
        )

        if shortage > 0:
            shortages[sku] = shortage

    return shortages


def create_demand_aligned_events(
    shortages: dict[str, Decimal],
    *,
    effective_day: Decimal = Decimal("3"),
) -> list[ScenarioEvent]:
    events: list[ScenarioEvent] = []

    for sku, quantity in sorted(shortages.items()):
        if quantity <= 0:
            continue

        events.append(
            ScenarioEvent(
                event_type="inventory_replenishment",
                effective_day=effective_day,
                payload={
                    "sku": sku,
                    "quantity": str(quantity),
                    "order_number": (f"DEMAND-ALIGNED-{sku}"),
                },
            )
        )

    return events
