from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal
from typing import Any, cast

from core.models import SnapshotBundle, SnapshotRecord
from core.serialization import canonical_data
from tools.inventory.reorder import build_reorder_recommendations
from tools.inventory.snapshot_adapter import extract_inventory_strategy_rows


class BusinessDashboardService:
    """Build read-only business views from one immutable Actual State snapshot."""

    def __init__(self, snapshot: SnapshotBundle) -> None:
        self.snapshot = snapshot

    def _records(self, record_type: str) -> list[SnapshotRecord]:
        return [record for record in self.snapshot.records if record.record_type == record_type]

    def _orders(self, object_type: str) -> list[SnapshotRecord]:
        return [
            record
            for record in self._records("business_object")
            if record.data.get("object_type") == object_type
        ]

    def sales(self) -> dict[str, Any]:
        orders = self._orders("sales_order")
        statuses = Counter(str(record.data["status"]) for record in orders)
        total_value = sum((Decimal(str(record.data["amount"])) for record in orders), Decimal())
        backlog = [record for record in orders if record.data["status"] == "backlog"]
        backlog_value = sum((Decimal(str(record.data["amount"])) for record in backlog), Decimal())
        fulfilled = sum(statuses[status] for status in ("paid", "shipped"))
        sku_totals: dict[str, dict[str, Decimal | int]] = defaultdict(
            lambda: {"orders": 0, "value": Decimal()}
        )
        for record in orders:
            details = record.data.get("details")
            sku = str(details.get("sku", "Unknown")) if isinstance(details, dict) else "Unknown"
            sku_totals[sku]["orders"] += 1
            sku_totals[sku]["value"] += Decimal(str(record.data["amount"]))

        top_skus = sorted(
            (
                {"sku": sku, "order_count": values["orders"], "order_value": values["value"]}
                for sku, values in sku_totals.items()
            ),
            key=lambda row: (-Decimal(str(row["order_value"])), str(row["sku"])),
        )[:8]
        backlog_rows = sorted(
            (
                {
                    "order_number": record.data["object_number"],
                    "sku": (
                        record.data["details"].get("sku", "Unknown")
                        if isinstance(record.data.get("details"), dict)
                        else "Unknown"
                    ),
                    "amount": record.data["amount"],
                    "quantity": record.data["quantity"],
                    "current_step": record.data["current_node_id"],
                    "priority": record.data["priority"],
                }
                for record in backlog
            ),
            key=lambda row: (-int(row["priority"]), -Decimal(str(row["amount"]))),
        )[:12]

        return cast(
            dict[str, Any],
            canonical_data(
                {
                    "summary": {
                        "order_count": len(orders),
                        "current_order_value": total_value,
                        "fulfilled_order_count": fulfilled,
                        "fulfilment_rate": (
                            Decimal(fulfilled) / Decimal(len(orders)) if orders else Decimal()
                        ),
                        "backlog_count": len(backlog),
                        "backlog_value": backlog_value,
                    },
                    "status_counts": dict(sorted(statuses.items())),
                    "top_skus": top_skus,
                    "backlog_orders": backlog_rows,
                    "measurement_note": (
                        "Order value is the imported current order amount. It is not recognised "
                        "revenue and is not a financial forecast."
                    ),
                }
            ),
        )

    def inventory(self) -> dict[str, Any]:
        items = self._records("item")
        inventory = self._records("inventory")
        item_by_id = {str(record.data["id"]): record.data for record in items}
        on_hand = sum((Decimal(str(record.data["quantity"])) for record in inventory), Decimal())
        inventory_value = sum(
            (
                Decimal(str(record.data["quantity"]))
                * Decimal(str(item_by_id[str(record.data["item_id"])]["standard_cost"]))
                for record in inventory
            ),
            Decimal(),
        )
        strategy_rows = extract_inventory_strategy_rows(self.snapshot)
        recommendations = build_reorder_recommendations(
            list(strategy_rows.item_rows), list(strategy_rows.inventory_rows)
        )
        candidates = [row for row in recommendations if row["needs_reorder"] == "true"]
        risk_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        candidates.sort(key=lambda row: (risk_order.get(row["risk_level"], 99), row["sku"]))
        risk_counts = Counter(row["risk_level"] for row in recommendations)

        return cast(
            dict[str, Any],
            canonical_data(
                {
                    "summary": {
                        "sku_count": len(items),
                        "warehouse_count": len(
                            {str(record.data["warehouse"]) for record in inventory}
                        ),
                        "on_hand_units": on_hand,
                        "inventory_value_at_standard_cost": inventory_value,
                        "reorder_candidate_count": len(candidates),
                        "critical_candidate_count": risk_counts["critical"],
                    },
                    "risk_counts": dict(sorted(risk_counts.items())),
                    "reorder_candidates": candidates,
                    "measurement_note": (
                        "Inventory value is quantity multiplied by source standard cost. Reorder "
                        "recommendations are deterministic rule outputs and require review."
                    ),
                }
            ),
        )

    def accounting(self) -> dict[str, Any]:
        balance_records = self._records("balance")
        balances = {
            str(record.data["account_code"]): Decimal(str(record.data["amount"]))
            for record in balance_records
        }
        revenue = balances.get("REVENUE", Decimal())
        cost_of_goods_sold = balances.get("COST_OF_GOODS_SOLD", Decimal())
        gross_profit = revenue - cost_of_goods_sold
        rows = sorted(
            (
                {
                    "account_code": record.data["account_code"],
                    "amount": record.data["amount"],
                    "currency": record.data["currency"],
                    "data_origin": record.data["data_origin"],
                }
                for record in balance_records
            ),
            key=lambda row: str(row["account_code"]),
        )

        return cast(
            dict[str, Any],
            canonical_data(
                {
                    "summary": {
                        "cash": balances.get("CASH", Decimal()),
                        "accounts_receivable": balances.get("ACCOUNTS_RECEIVABLE", Decimal()),
                        "accounts_payable": balances.get("ACCOUNTS_PAYABLE", Decimal()),
                        "gross_profit": gross_profit,
                        "gross_margin": gross_profit / revenue if revenue else Decimal(),
                        "working_capital": (
                            balances.get("CASH", Decimal())
                            + balances.get("ACCOUNTS_RECEIVABLE", Decimal())
                            + balances.get("INVENTORY", Decimal())
                            - balances.get("ACCOUNTS_PAYABLE", Decimal())
                        ),
                    },
                    "balances": rows,
                    "measurement_note": (
                        "These are synthetic opening balances for the demo. Gross profit and "
                        "working capital are deterministic derived indicators, not audited "
                        "statements."
                    ),
                }
            ),
        )

    def operations(self) -> dict[str, Any]:
        objects = self._records("business_object")
        resources = self._records("resource")
        process_counts = Counter(str(record.data["process_id"]) for record in objects)
        node_counts = Counter(str(record.data["current_node_id"]) for record in objects)
        resource_rows = sorted(
            (
                {
                    "process_id": record.data["process_id"],
                    "node_id": record.data["node_id"],
                    "resource_type": record.data["resource_type"],
                    "capacity_units": record.data["capacity_units"],
                    "data_origin": record.data["data_origin"],
                }
                for record in resources
            ),
            key=lambda row: (str(row["process_id"]), str(row["node_id"])),
        )
        return cast(
            dict[str, Any],
            canonical_data(
                {
                    "summary": {
                        "business_object_count": len(objects),
                        "process_count": len(process_counts),
                        "active_node_count": len(node_counts),
                        "resource_count": len(resources),
                        "order_to_cash_objects": process_counts["order_to_cash"],
                        "procure_to_pay_objects": process_counts["procure_to_pay"],
                    },
                    "process_counts": dict(sorted(process_counts.items())),
                    "objects_by_current_node": [
                        {"node_id": node, "object_count": count}
                        for node, count in sorted(
                            node_counts.items(), key=lambda item: (-item[1], item[0])
                        )
                    ],
                    "resources": resource_rows,
                    "measurement_note": (
                        "Counts describe the current imported state. Historical cycle time "
                        "requires event history and is therefore not inferred here."
                    ),
                }
            ),
        )

    def overview(self, crm_summary: dict[str, Any]) -> dict[str, Any]:
        sales = self.sales()["summary"]
        inventory = self.inventory()["summary"]
        accounting = self.accounting()["summary"]
        operations = self.operations()["summary"]
        return {
            "headline": {
                "current_order_value": sales["current_order_value"],
                "backlog_count": sales["backlog_count"],
                "reorder_candidate_count": inventory["reorder_candidate_count"],
                "cash": accounting["cash"],
                "open_complaints": crm_summary["complaintCount"],
                "overdue_complaints": crm_summary["overdueComplaints"],
            },
            "modules": [
                {
                    "id": "sales",
                    "label": "Sales",
                    "signal": f"{sales['backlog_count']} backlog orders",
                },
                {
                    "id": "inventory",
                    "label": "Inventory",
                    "signal": f"{inventory['reorder_candidate_count']} reorder candidates",
                },
                {
                    "id": "accounting",
                    "label": "Accounting",
                    "signal": f"SGD {accounting['cash']} cash balance",
                },
                {
                    "id": "operations",
                    "label": "Operations",
                    "signal": f"{operations['business_object_count']} active business objects",
                },
                {
                    "id": "crm",
                    "label": "Customer Relationships",
                    "signal": f"{crm_summary['complaintCount']} complaints in queue",
                },
            ],
        }
