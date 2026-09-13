from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from business_coordinator.domain.models import SnapshotBundle


@dataclass(frozen=True)
class SimulatedOrder:
    object_id: str
    object_number: str
    object_type: str
    current_node_id: str
    status: str
    amount: Decimal
    quantity: Decimal
    priority: int
    sku: str
    due_at: datetime


@dataclass
class SimulationState:
    inventory: dict[str, Decimal]
    item_costs: dict[str, Decimal]
    item_prices: dict[str, Decimal]
    resource_capacities: dict[str, int]
    balances: dict[str, Decimal]
    orders: list[SimulatedOrder]


def _decimal(value: object) -> Decimal:
    return Decimal(str(value))


def snapshot_to_state(snapshot: SnapshotBundle) -> SimulationState:
    """Build a mutable simulation state without retaining snapshot references."""
    records = [deepcopy(record.model_dump(mode="python")) for record in snapshot.records]
    items_by_id: dict[str, dict[str, Any]] = {}
    item_costs: dict[str, Decimal] = {}
    item_prices: dict[str, Decimal] = {}
    inventory: dict[str, Decimal] = {}
    resources: dict[str, int] = {}
    balances: dict[str, Decimal] = {}
    orders: list[SimulatedOrder] = []

    for record in records:
        data = record["data"]
        if record["record_type"] == "item":
            items_by_id[str(data["id"])] = data
            item_costs[str(data["sku"])] = _decimal(data["standard_cost"])
            item_prices[str(data["sku"])] = _decimal(data["list_price"])

    for record in records:
        data = record["data"]
        record_type = record["record_type"]
        if record_type == "inventory":
            item = items_by_id[str(data["item_id"])]
            sku = str(item["sku"])
            inventory[sku] = inventory.get(sku, Decimal("0")) + _decimal(data["quantity"])
        elif record_type == "resource":
            resource_type = str(data["resource_type"])
            capacity = max(1, int(_decimal(data["capacity_units"])))
            # A resource type is one shared pool even when multiple nodes consume it.
            resources[resource_type] = max(resources.get(resource_type, 0), capacity)
        elif record_type == "balance":
            balances[str(data["account_code"])] = _decimal(data["amount"])
        elif record_type == "business_object":
            details = data.get("details", {})
            sku = str(details.get("sku", ""))
            due_value = details.get("due_date", data["entered_node_at"])
            orders.append(
                SimulatedOrder(
                    object_id=str(data["id"]),
                    object_number=str(data["object_number"]),
                    object_type=str(data["object_type"]),
                    current_node_id=str(data["current_node_id"]),
                    status=str(data["status"]),
                    amount=_decimal(data["amount"]),
                    quantity=_decimal(data["quantity"]),
                    priority=int(data["priority"]),
                    sku=sku,
                    due_at=datetime.fromisoformat(str(due_value)),
                )
            )

    missing_skus = sorted(order.object_number for order in orders if not order.sku)
    if missing_skus:
        raise ValueError(f"snapshot business objects are missing SKU details: {missing_skus[:3]}")
    required_balances = {"CASH", "ACCOUNTS_RECEIVABLE", "ACCOUNTS_PAYABLE"}
    missing_balances = sorted(required_balances - balances.keys())
    if missing_balances:
        raise ValueError(f"snapshot is missing opening balances: {missing_balances}")
    required_resources = {"sales_staff", "warehouse_staff", "finance_staff", "purchasing_staff"}
    missing_resources = sorted(required_resources - resources.keys())
    if missing_resources:
        raise ValueError(f"snapshot is missing resource capacity: {missing_resources}")
    return SimulationState(
        inventory=inventory,
        item_costs=item_costs,
        item_prices=item_prices,
        resource_capacities=resources,
        balances=balances,
        orders=sorted(orders, key=lambda order: (order.priority, order.object_number)),
    )
