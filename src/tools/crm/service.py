from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from core.models import SnapshotBundle
from core.serialization import canonical_data


def _money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")


def _percentile(value: Decimal, values: list[Decimal]) -> float:
    return sum(candidate <= value for candidate in values) / len(values) if values else 0.0


class CRMService:
    """Read-only CRM projection of the same immutable snapshot used by Sales/Inventory.

    Cases are derived order-service exceptions, NOT imported customer complaints.
    No reviews, response records, replacement stock or policy assumptions are fabricated.
    """

    def __init__(self, snapshot: SnapshotBundle) -> None:
        self.snapshot = snapshot
        self.snapshot_time = snapshot.manifest.as_of_time.isoformat()
        self.dataset_fingerprint = snapshot.manifest.content_hash
        self.currency = "SGD"
        self.customers = {
            record.record_key: deepcopy(record.data)
            for record in snapshot.records
            if record.record_type == "customer"
        }
        self.items = {
            str(record.data["sku"]): deepcopy(record.data)
            for record in snapshot.records
            if record.record_type == "item"
        }
        sku_by_id = {str(row["id"]): sku for sku, row in self.items.items()}
        self.stock: dict[str, Decimal] = defaultdict(Decimal)
        self.warehouses: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for record in snapshot.records:
            if record.record_type == "inventory":
                sku = sku_by_id.get(str(record.data["item_id"]))
                if sku:
                    self.stock[sku] += Decimal(str(record.data["quantity"]))
                    self.warehouses[sku].append(deepcopy(record.data))
        self.orders = {
            str(record.data["object_number"]): deepcopy(record.data)
            for record in snapshot.records
            if record.record_type == "business_object"
            and record.data["object_type"] == "sales_order"
        }
        self.pending: dict[str, Decimal] = defaultdict(Decimal)
        self.cases: dict[str, dict[str, Any]] = {}
        as_of = snapshot.manifest.as_of_time
        for number, order in sorted(self.orders.items()):
            details = order["details"]
            if details["customer_number"] not in self.customers:
                raise ValueError("Sales order customer is missing from the canonical snapshot")
            if details["sku"] not in self.items:
                raise ValueError("Sales order item is missing from the canonical snapshot")
            if order["status"] not in {"open", "backlog"}:
                continue
            self.pending[str(details["sku"])] += Decimal(str(order["quantity"]))
            due = datetime.fromisoformat(str(details["due_date"]))
            if order["status"] != "backlog" and due >= as_of:
                continue
            overdue = max(0.0, (as_of - due).total_seconds() / 3600)
            case_id = f"CASE-{number}"
            self.cases[case_id] = {
                "id": case_id,
                "customerId": str(details["customer_number"]),
                "orderId": number,
                "orderObjectId": str(order["id"]),
                "sku": str(details["sku"]),
                "quantity": str(order["quantity"]),
                "issue": f"Order {order['status']}; fulfilment requires review",
                "status": "WAITING_FULFILMENT",
                "openedAt": None,
                "firstResponseAt": None,
                "reviewScore": None,
                "dueAt": due.isoformat(),
                "orderDate": str(details["order_date"]),
                "lateDays": int(overdue // 24),
                "overdueHours": round(overdue, 2),
                "caseKind": "derived_order_service_exception",
                "dueBasis": "Order due date, not a complaint SLA",
                "orderStatus": str(order["status"]),
                "orderAmount": _money(Decimal(str(order["amount"]))),
                "snapshotId": self.reference_id,
                "snapshotHash": self.dataset_fingerprint,
                "lineage": {
                    key: order[key]
                    for key in (
                        "source_system",
                        "source_file_id",
                        "source_record_id",
                        "ingestion_run_id",
                        "data_origin",
                    )
                },
            }

    @property
    def reference_id(self) -> str:
        return self.snapshot.manifest.snapshot_id

    def provenance(self) -> dict[str, Any]:
        return {
            "dataset_id": "adventureworks-unified-snapshot-v1",
            "reference_id": self.reference_id,
            "snapshot_id": self.reference_id,
            "company_id": self.snapshot.manifest.company_id,
            "dataset": "Unified AdventureWorks Enterprise State",
            "as_of": self.snapshot_time,
            "fingerprint": self.dataset_fingerprint,
            "currency": self.currency,
            "boundaries": {
                "source": [
                    "Detached snapshot customer/item/order/inventory records and their lineage"
                ],
                "derived": [
                    "Order-service exceptions from backlog/overdue pending orders",
                    "Customer ordered-value score (not payment/spend)",
                    "Fulfilment risk and service priority",
                    "Pending SKU obligations (not warehouse reservations)",
                ],
                "synthetic": [],
            },
            "upstream_data_origins": sorted(
                {
                    str(record.data["data_origin"])
                    for record in self.snapshot.records
                    if "data_origin" in record.data
                }
            ),
            "unavailable": [
                "Customer complaints/reviews",
                "First-response records",
                "Complaint SLA",
                "Confirmed delivery timestamp",
                "Refund eligibility/payment detail",
                "Credit policy",
                "Logistics cost",
                "Promised resolution ETA",
            ],
            "warning": (
                "Customer value and relationship risk are service signals, not credit ratings. "
                "Cases are derived order exceptions, not actual customer complaints. "
                "Upstream source/derived/synthetic lineage remains unchanged."
            ),
        }

    def rate_customers(self) -> list[dict[str, Any]]:
        own_orders: dict[str, list[dict[str, Any]]] = defaultdict(list)
        own_cases: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for order in self.orders.values():
            own_orders[str(order["details"]["customer_number"])].append(order)
        for case in self.cases.values():
            own_cases[str(case["customerId"])].append(case)
        totals = {
            key: sum((Decimal(str(row["amount"])) for row in rows), Decimal(0))
            for key, rows in own_orders.items()
        }
        counts = {key: Decimal(len(own_orders[key])) for key in self.customers}
        result = []
        for key, customer in sorted(self.customers.items()):
            orders, cases = own_orders[key], own_cases[key]
            total = totals.get(key, Decimal(0))
            value = (
                round(
                    70 * _percentile(total, list(totals.values()))
                    + 30 * _percentile(counts[key], list(counts.values()))
                )
                if orders
                else 0
            )
            overdue = sum(case["overdueHours"] > 0 for case in cases)
            risk = min(100, len(cases) * 20 + overdue * 15)
            result.append(
                {
                    "id": key,
                    "customerNumber": key,
                    "name": customer["name"],
                    "active": customer["active"],
                    "orderCount": len(orders),
                    "orderedValue": _money(total),
                    "currency": self.currency,
                    "lastOrderAt": max(
                        (str(row["details"]["order_date"]) for row in orders), default=None
                    ),
                    "valueScore": value,
                    "valueTier": "A"
                    if value >= 75
                    else "B"
                    if value >= 50
                    else "C"
                    if orders
                    else "Prospect",
                    "riskScore": risk,
                    "riskLevel": "High" if risk >= 65 else "Medium" if risk >= 35 else "Low",
                    "openCases": len(cases),
                    "overdueCases": overdue,
                    "unrespondedComplaints": None,
                    "scoreReasons": [
                        f"{len(orders)} orders; SGD {total:.2f} ordered value, not paid spend.",
                        f"{len(cases)} derived service cases; {overdue} orders past due.",
                    ],
                    "nextAction": "Review fulfilment with warehouse before preparing an update."
                    if cases
                    else "No pending order-service exception.",
                    "lineage": {
                        field: customer[field]
                        for field in (
                            "source_system",
                            "source_file_id",
                            "source_record_id",
                            "data_origin",
                        )
                    },
                }
            )
        return result

    def customer(self, customer_id: str) -> dict[str, Any]:
        identifier = customer_id.upper()
        customer = next((row for row in self.rate_customers() if row["id"] == identifier), None)
        if customer is None:
            raise ValueError(f"Customer {identifier} was not found in the request snapshot")
        return {
            **customer,
            "cases": [
                row for row in self.prioritize_complaints() if row["customerId"] == identifier
            ],
            "boundary": "Ordered value and derived risk; not payments or credit ratings.",
        }

    def prioritize_complaints(self) -> list[dict[str, Any]]:
        """Compatibility name: returns derived order-service cases, NOT complaints."""
        customers = {row["id"]: row for row in self.rate_customers()}
        rows = []
        for case in self.cases.values():
            customer = customers[case["customerId"]]
            priority = min(
                100,
                round(35 + min(50, case["overdueHours"] / 24 * 5) + customer["riskScore"] * 0.1),
            )
            rows.append(
                {
                    **deepcopy(case),
                    "customer": customer,
                    "priorityScore": priority,
                    "priorityLevel": "Critical"
                    if priority >= 70
                    else "High"
                    if priority >= 50
                    else "Standard",
                    "reasons": [
                        f"Snapshot order status: {case['orderStatus']}",
                        f"{case['overdueHours']:.2f}h past order due date; not complaint SLA",
                        "Derived priority; reviews and first-response data are unavailable",
                    ],
                    "ownerRole": "CRM + Fulfilment",
                    "nextAction": "Verify stock and fulfilment before confirming next steps.",
                    "replyDraft": self.draft_reply(case["id"], "professional")["draft"],
                    "internalDraft": f"{case['orderId']}/{case['sku']}; {self.reference_id}.",
                }
            )
        return sorted(rows, key=lambda row: (-row["priorityScore"], row["id"]))

    def complaint(self, complaint_id: str) -> dict[str, Any]:
        identifier = complaint_id.upper()
        row = next((row for row in self.prioritize_complaints() if row["id"] == identifier), None)
        if row is None:
            raise ValueError(f"Service case {identifier} was not found in the request snapshot")
        return row

    def summary(self) -> dict[str, Any]:
        customers = self.rate_customers()
        cases = self.prioritize_complaints()
        return {
            "customerCount": len(customers),
            "salesOrderCount": len(self.orders),
            "serviceCaseCount": len(cases),
            "complaintCount": None,
            "highRiskCustomers": sum(row["riskLevel"] == "High" for row in customers),
            "overdueOrders": sum(row["overdueHours"] > 0 for row in cases),
            "overdueComplaints": None,
            "unrespondedComplaints": None,
            "aTierCustomers": sum(row["valueTier"] == "A" for row in customers),
            "currency": self.currency,
            "snapshotId": self.reference_id,
            "caseBasis": "Derived backlog/overdue pending-order exceptions; no imported complaints",
        }

    def order_timeline(self, complaint_id: str) -> list[dict[str, Any]]:
        case = self.complaint(complaint_id)
        return [
            {
                "label": "Order placed",
                "at": case["orderDate"],
                "kind": "Snapshot record",
                "detail": case["orderId"],
            },
            {
                "label": "Order due date",
                "at": case["dueAt"],
                "kind": "Snapshot record",
                "detail": "Order deadline; no complaint SLA",
            },
            {
                "label": "Status at snapshot",
                "at": self.snapshot_time,
                "kind": "Snapshot record",
                "detail": case["orderStatus"],
            },
        ]

    def inventory_availability(self, complaint_id: str) -> dict[str, Any]:
        case = self.complaint(complaint_id)
        sku = case["sku"]
        on_hand, obligations = self.stock[sku], self.pending[sku]
        return {
            "sku": sku,
            "onHandUnits": str(on_hand),
            "pendingOrderUnits": str(obligations),
            "availableUnits": str(max(Decimal(0), on_hand - obligations)),
            "availableForThisOrder": str(
                max(Decimal(0), on_hand - max(Decimal(0), obligations - Decimal(case["quantity"])))
            ),
            "orderQuantity": case["quantity"],
            "warehouses": canonical_data(self.warehouses[sku]),
            "snapshotId": self.reference_id,
            "replenishmentDays": None,
            "basis": "Same snapshot inventory; availability nets ALL pending sales obligations. "
            "availableForThisOrder excludes the current order's own obligation. "
            "This is not a warehouse reservation or replacement-stock record.",
        }

    def financial_impact(self, complaint_id: str) -> dict[str, Any]:
        case = self.complaint(complaint_id)
        item = self.items[case["sku"]]
        amount = Decimal(case["orderAmount"])
        standard_cost = Decimal(str(item["standard_cost"])) * Decimal(case["quantity"])
        return {
            "currency": self.currency,
            "orderAmount": _money(amount),
            "fullRefundExposure": _money(amount),
            "fulfilmentStandardCost": _money(standard_cost),
            "serviceCreditEstimate": None,
            "paymentVerified": False,
            "basis": [
                "Order amount is from the same immutable snapshot, not an average-spend proxy.",
                "Refund exposure is conditional; paid amount and refund eligibility are unknown.",
                "Snapshot standard cost times quantity; not a booked expense.",
                "Credit, logistics fees and resolution ETA are unavailable; no policy is invented.",
            ],
        }

    def resolution_options(self, complaint_id: str) -> list[dict[str, Any]]:
        case = self.complaint(complaint_id)
        inventory, financial = (
            self.inventory_availability(complaint_id),
            self.financial_impact(complaint_id),
        )
        stock_feasible = Decimal(inventory["availableForThisOrder"]) >= Decimal(case["quantity"])
        recommended = "reship" if stock_feasible else "monitor"
        return [
            {
                "id": "refund",
                "label": "Review cancellation / refund eligibility",
                "estimatedCost": financial["fullRefundExposure"],
                "currency": self.currency,
                "resolutionDays": None,
                "feasible": True,
                "recommended": False,
                "conditions": "Finance must verify payment, cancellation and refund eligibility.",
                "risk": "Exposure estimate only; no payment or refund is confirmed.",
            },
            {
                "id": "reship",
                "label": "Review stock allocation / fulfilment",
                "estimatedCost": financial["fulfilmentStandardCost"],
                "currency": self.currency,
                "resolutionDays": None,
                "feasible": stock_feasible,
                "recommended": recommended == "reship",
                "conditions": "Snapshot stock net of OTHER pending orders must cover this order.",
                "risk": "Derived obligations, not actual reservations; warehouse must verify.",
            },
            {
                "id": "credit",
                "label": "Service credit (policy unavailable)",
                "estimatedCost": None,
                "currency": self.currency,
                "resolutionDays": None,
                "feasible": False,
                "recommended": False,
                "conditions": "No credit policy was provided.",
                "risk": "Do not invent compensation.",
            },
            {
                "id": "monitor",
                "label": "Investigate fulfilment and prepare update",
                "estimatedCost": "0.00",
                "currency": self.currency,
                "resolutionDays": None,
                "feasible": True,
                "recommended": recommended == "monitor",
                "conditions": "Verify fulfilment and shortage before making commitments.",
                "risk": "Delay possible; zero means no proposed transaction, not no service cost.",
            },
        ]

    def investigate(self, complaint_id: str) -> dict[str, Any]:
        case = self.complaint(complaint_id)
        options = self.resolution_options(complaint_id)
        recommendation = next(row for row in options if row["recommended"])
        return {
            "complaintId": case["id"],
            "caseKind": case["caseKind"],
            "customerId": case["customerId"],
            "orderId": case["orderId"],
            "orderObjectId": case["orderObjectId"],
            "priority": f"{case['priorityLevel']}/{case['priorityScore']}",
            "timeline": self.order_timeline(complaint_id),
            "inventory": self.inventory_availability(complaint_id),
            "financial": self.financial_impact(complaint_id),
            "options": options,
            "recommendation": recommendation,
            "rationale": "Snapshot availability supports a fulfilment review."
            if recommendation["id"] == "reship"
            else "Pending demand consumes snapshot stock; investigate before making commitments.",
            "boundary": "Same canonical AdventureWorks snapshot as Sales/Inventory. "
            "Cases/priorities are derived order exceptions, not customer complaints. "
            "No reviews, complaint SLA, payment eligibility or resolution ETA is provided.",
        }

    def draft_reply(self, complaint_id: str, tone: str) -> dict[str, Any]:
        case = self.cases.get(complaint_id.upper())
        if case is None:
            raise ValueError("Service case was not found in the request snapshot")
        prefix = (
            "Hello, we are sorry about the fulfilment delay." if tone == "empathetic" else "Hello,"
        )
        return {
            "complaintId": case["id"],
            "status": "Unsent draft",
            "draft": f"{prefix} We are checking the fulfilment of order {case['orderId']}. "
            "A team member will verify stock and the next step before confirming a resolution.",
            "verifiedFacts": {
                "orderId": case["orderId"],
                "orderStatus": case["orderStatus"],
                "dueAt": case["dueAt"],
                "snapshotId": self.reference_id,
            },
        }
