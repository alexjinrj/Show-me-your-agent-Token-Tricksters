from __future__ import annotations

import json
import math
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal


def _hours_between(later: str, earlier: str) -> float:
    return max(
        0.0,
        (datetime.fromisoformat(later) - datetime.fromisoformat(earlier)).total_seconds() / 3600,
    )


def _percentile(value: float, values: list[float]) -> float:
    return sum(candidate <= value for candidate in values) / len(values) if values else 0.0


def _js_round(value: float) -> int:
    return math.floor(value + 0.5)


def _money(value: float) -> float:
    return math.floor(value * 100 + 0.5) / 100


class CRMService:
    """Read-only CRM demo state with explicit Olist/replay/assumption provenance."""

    def __init__(self, dataset_path: Path) -> None:
        raw = dataset_path.read_bytes()
        payload = json.loads(raw)
        self.dataset_path = dataset_path
        self.dataset_fingerprint = sha256(raw).hexdigest()
        self.meta: dict[str, Any] = payload["meta"]
        self.snapshot_time = str(self.meta["replayAsOf"])
        self.customers: list[dict[str, Any]] = [
            self._normalise_customer(row) for row in payload["customers"]
        ]
        self.complaints: list[dict[str, Any]] = [
            self._normalise_complaint(row) for row in payload["complaints"]
        ]

    @property
    def reference_id(self) -> str:
        return f"olist-crm-demo:{self.dataset_fingerprint[:16]}"

    def provenance(self) -> dict[str, Any]:
        return {
            "dataset_id": "olist-crm-demo-v1",
            "reference_id": self.reference_id,
            "dataset": self.meta["dataset"],
            "source_url": self.meta["sourceUrl"],
            "source_period": self.meta["sourcePeriod"],
            "replay_as_of": self.snapshot_time,
            "fingerprint": self.dataset_fingerprint,
            "boundaries": {
                "source": self.meta["realFields"],
                "derived": [
                    "customer value score and tier",
                    "relationship risk score and level",
                    "complaint priority and recommended next action",
                ],
                "synthetic": self.meta["simulatedFields"]
                + ["replacement inventory", "resolution cost assumptions"],
            },
            "warning": (
                "Customer value and relationship risk are service signals, not credit ratings."
            ),
        }

    @staticmethod
    def _normalise_customer(row: dict[str, Any]) -> dict[str, Any]:
        result = deepcopy(row)
        result["name"] = f"Olist Anonymous Customer {str(row['id'])[-3:]}"
        result["type"] = "Anonymous"
        result["onboarding"] = "Not provided"
        if result.get("paymentTerms") == "数据未提供":
            result["paymentTerms"] = "Not provided"
        return result

    @staticmethod
    def _normalise_complaint(row: dict[str, Any]) -> dict[str, Any]:
        result = deepcopy(row)
        review = row.get("reviewScore")
        late_days = int(row.get("lateDays", 0))
        if review is not None and late_days > 0:
            result["issue"] = f"{review}/5 review; delivered {late_days} days late"
        elif review is not None:
            result["issue"] = f"{review}/5 customer review"
        else:
            result["issue"] = f"Delivery exception; {late_days} days late"
        return result

    def _value_score(self, customer: dict[str, Any]) -> int:
        if not customer["orderCount"]:
            return 0
        spend = _percentile(float(customer["spend"]), [float(c["spend"]) for c in self.customers])
        frequency = _percentile(
            float(customer["orderCount"]), [float(c["orderCount"]) for c in self.customers]
        )
        recency = _percentile(
            datetime.fromisoformat(customer["lastOrderAt"]).timestamp(),
            [datetime.fromisoformat(c["lastOrderAt"]).timestamp() for c in self.customers],
        )
        return min(100, _js_round(spend * 50 + frequency * 30 + recency * 20))

    @staticmethod
    def _value_tier(score: int, order_count: int) -> str:
        if not order_count:
            return "Prospect"
        if score >= 75:
            return "A"
        if score >= 50:
            return "B"
        return "C"

    @staticmethod
    def _risk_score(
        open_count: int,
        overdue: int,
        unresponded: int,
        review_penalty: int,
        late_deliveries: int,
    ) -> int:
        return min(
            100,
            open_count * 10
            + overdue * 15
            + unresponded * 20
            + review_penalty
            + min(20, late_deliveries * 10),
        )

    def rate_customers(self) -> list[dict[str, Any]]:
        rated: list[dict[str, Any]] = []
        replay_as_of = datetime.fromisoformat(self.snapshot_time)
        for customer in self.customers:
            own = [ticket for ticket in self.complaints if ticket["customerId"] == customer["id"]]
            overdue = sum(datetime.fromisoformat(ticket["dueAt"]) < replay_as_of for ticket in own)
            unresponded = sum(not ticket.get("firstResponseAt") for ticket in own)
            low_reviews = [
                ticket
                for ticket in own
                if ticket.get("reviewScore") is not None and ticket["reviewScore"] <= 2
            ]
            review_penalty = sum(20 if ticket["reviewScore"] == 1 else 10 for ticket in low_reviews)
            value = self._value_score(customer)
            risk = self._risk_score(
                len(own), overdue, unresponded, review_penalty, int(customer["lateDeliveryCount"])
            )
            rated.append(
                {
                    **deepcopy(customer),
                    "valueScore": value,
                    "valueTier": self._value_tier(value, int(customer["orderCount"])),
                    "riskScore": risk,
                    "riskLevel": "High" if risk >= 65 else "Medium" if risk >= 35 else "Low",
                    "openComplaints": len(own),
                    "overdueComplaints": overdue,
                    "unrespondedComplaints": unresponded,
                    "scoreReasons": [
                        (
                            f"Olist facts: R$ {float(customer['spend']):.2f} paid, "
                            f"{customer['orderCount']} order(s), last order "
                            f"{customer['lastOrderAt'][:10]}"
                        ),
                        (
                            f"Experience signals: {len(low_reviews)} low review(s), "
                            f"{customer['lateDeliveryCount']} late delivery event(s); "
                            f"CRM replay: {len(own)} open, {overdue} overdue, "
                            f"{unresponded} unresponded"
                        ),
                    ],
                    "nextAction": (
                        (
                            "Verify that no reply is missing, then acknowledge the "
                            "complaint immediately."
                        )
                        if unresponded
                        else (
                            "Ask fulfilment to verify the order timeline and provide "
                            "a fact-based update."
                        )
                        if overdue
                        else (
                            "Review the original feedback and prepare an evidence-based "
                            "recovery plan."
                        )
                        if low_reviews
                        else "No urgent relationship action; continue normal engagement."
                    ),
                }
            )
        return rated

    def customer(self, customer_id: str) -> dict[str, Any]:
        identifier = customer_id.upper()
        customer = next((row for row in self.rate_customers() if row["id"] == identifier), None)
        if customer is None:
            raise ValueError(f"Customer {identifier} was not found")
        return {
            **customer,
            "complaints": [
                row for row in self.prioritize_complaints() if row["customerId"] == identifier
            ],
            "boundary": (
                "Value uses Olist payment, frequency and recency. Risk uses Olist "
                "review/delivery signals plus labelled CRM replay fields. This is "
                "not a credit rating."
            ),
        }

    def prioritize_complaints(self) -> list[dict[str, Any]]:
        customers = {customer["id"]: customer for customer in self.rate_customers()}
        ownership: dict[str, tuple[str, str]] = {
            "READY": (
                "Customer Service",
                "Verify the review and order timeline before responding.",
            ),
            "WAITING_WAREHOUSE": (
                "CRM + Fulfilment",
                "Verify promised and actual delivery dates and the delay cause.",
            ),
            "WAITING_FINANCE": (
                "CRM + Finance",
                "Verify refund eligibility and status before making a commitment.",
            ),
            "WAITING_CUSTOMER": (
                "Customer Service",
                "Send one clear request for the missing customer information.",
            ),
        }
        results: list[dict[str, Any]] = []
        for ticket in self.complaints:
            customer = customers[ticket["customerId"]]
            overdue_hours = _hours_between(self.snapshot_time, ticket["dueAt"])
            age_hours = _hours_between(self.snapshot_time, ticket["openedAt"])
            sla_points = min(40.0, overdue_hours / 48 * 40)
            review_points = (
                20
                if ticket.get("reviewScore") == 1
                else 12
                if ticket.get("reviewScore") == 2
                else 0
            )
            late_points = min(10.0, int(ticket["lateDays"]) / 2)
            priority = min(
                100,
                _js_round(
                    sla_points
                    + (25 if not ticket.get("firstResponseAt") else 0)
                    + review_points
                    + late_points
                    + customer["riskScore"] * 0.05
                    + customer["valueScore"] * 0.02
                ),
            )
            owner, base_action = ownership[ticket["status"]]
            reasons = [
                f"Olist fact: {ticket.get('reviewScore', 'no')}-star review"
                + (f" and {ticket['lateDays']} days late" if ticket["lateDays"] > 0 else ""),
                f"CRM replay: SLA overdue by {overdue_hours:.1f} hours"
                if overdue_hours
                else (
                    "CRM replay: "
                    f"{_hours_between(ticket['dueAt'], self.snapshot_time):.1f} "
                    "hours before SLA"
                ),
                "CRM replay: first response recorded"
                if ticket.get("firstResponseAt")
                else "CRM replay: no first response recorded",
                (
                    f"Customer value {customer['valueTier']}/"
                    f"{customer['valueScore']} contributes only 2% of priority"
                ),
            ]
            next_action = (
                (
                    "Confirm there is no unsynchronised reply, acknowledge the "
                    f"customer, then {base_action.lower()}"
                )
                if not ticket.get("firstResponseAt")
                else base_action
            )
            results.append(
                {
                    **deepcopy(ticket),
                    "customer": customer,
                    "priorityScore": priority,
                    "priorityLevel": "Critical"
                    if priority >= 70
                    else "High"
                    if priority >= 50
                    else "Standard",
                    "overdueHours": round(overdue_hours, 2),
                    "ageHours": round(age_hours, 2),
                    "reasons": reasons,
                    "ownerRole": owner,
                    "nextAction": next_action,
                    "replyDraft": (
                        "Hello, we have received your feedback about order "
                        f"{ticket['orderId']}. We are verifying the order and "
                        "delivery timeline and will update you after review. "
                        "This draft has not been sent."
                    ),
                    "internalDraft": (
                        f"{owner}: verify {ticket['id']} / {ticket['orderId']}, "
                        "record the evidence and response time, then return the "
                        "case to CRM."
                    ),
                }
            )
        return sorted(results, key=lambda row: (-row["priorityScore"], row["id"]))

    def complaint(self, complaint_id: str) -> dict[str, Any]:
        identifier = complaint_id.upper()
        complaint = next(
            (row for row in self.prioritize_complaints() if row["id"] == identifier), None
        )
        if complaint is None:
            raise ValueError(f"Complaint {identifier} was not found")
        return complaint

    def summary(self) -> dict[str, Any]:
        customers = self.rate_customers()
        complaints = self.prioritize_complaints()
        return {
            "customerCount": len(customers),
            "complaintCount": len(complaints),
            "highRiskCustomers": sum(row["riskLevel"] == "High" for row in customers),
            "overdueComplaints": sum(row["overdueHours"] > 0 for row in complaints),
            "unrespondedComplaints": sum(not row.get("firstResponseAt") for row in complaints),
            "aTierCustomers": sum(row["valueTier"] == "A" for row in customers),
            "lowReviewComplaints": sum((row.get("reviewScore") or 5) <= 2 for row in complaints),
            "lateDeliveryComplaints": sum(row["lateDays"] > 0 for row in complaints),
        }

    def order_timeline(self, complaint_id: str) -> list[dict[str, Any]]:
        ticket = self.complaint(complaint_id)
        return [
            {
                "label": "Order placed",
                "at": ticket["sourcePurchaseAt"],
                "kind": "Olist fact",
                "detail": ticket["sourceOrderId"],
            },
            {
                "label": "Promised delivery",
                "at": ticket["sourceEstimatedDeliveryAt"],
                "kind": "Olist fact",
                "detail": "Estimated delivery date in the Olist source record",
            },
            {
                "label": "Delivered",
                "at": ticket["sourceDeliveredAt"],
                "kind": "Olist fact",
                "detail": f"{ticket['lateDays']} days after the estimate"
                if ticket["lateDays"] > 0
                else "No recorded delay",
            },
            {
                "label": "Complaint opened",
                "at": ticket["openedAt"],
                "kind": "CRM replay",
                "detail": ticket["issue"],
            },
            {
                "label": "SLA deadline",
                "at": ticket["dueAt"],
                "kind": "CRM replay",
                "detail": f"{ticket['overdueHours']:.1f} hours overdue"
                if ticket["overdueHours"] > 0
                else "Within SLA",
            },
        ]

    def inventory_availability(self, complaint_id: str) -> dict[str, Any]:
        ticket = self.complaint(complaint_id)
        numeric_id = int(ticket["id"][-3:])
        return {
            "replacementSku": f"REPL-{ticket['sourceOrderId'][:6].upper()}",
            "availableUnits": (numeric_id * 7) % 5,
            "reservedUnits": numeric_id % 3,
            "replenishmentDays": 4 + numeric_id % 5,
            "kind": "Demo assumption",
        }

    def financial_impact(self, complaint_id: str) -> dict[str, Any]:
        ticket = self.complaint(complaint_id)
        proxy = _money(
            float(ticket["customer"]["spend"]) / max(int(ticket["customer"]["orderCount"]), 1)
        )
        return {
            "currency": "BRL",
            "orderValueProxy": proxy,
            "fullRefundExposure": proxy,
            "replacementCostEstimate": _money(proxy * 0.42 + 35),
            "serviceCreditEstimate": _money(min(proxy * 0.1, 150)),
            "basis": [
                "Order value is proxied from customer payment total divided by order count.",
                "Replacement cost assumes 42% product cost plus R$35 handling and delivery.",
                "Service credit is 10% of proxy order value, capped at R$150.",
                "All cost estimates are demo assumptions, not Olist accounting facts.",
            ],
        }

    def resolution_options(self, complaint_id: str) -> list[dict[str, Any]]:
        ticket = self.complaint(complaint_id)
        inventory = self.inventory_availability(complaint_id)
        financial = self.financial_impact(complaint_id)
        recommended: Literal["refund", "reship"] = (
            "refund"
            if ticket.get("reviewScore") == 1 and ticket["lateDays"] >= 30
            else "reship"
            if inventory["availableUnits"] > 0
            else "refund"
        )
        return [
            {
                "id": "refund",
                "label": "Full refund",
                "estimatedCost": financial["fullRefundExposure"],
                "resolutionDays": 2,
                "relationshipRecovery": "High",
                "feasible": True,
                "conditions": "Requires finance approval and verified refund eligibility.",
                "risk": "Highest direct cost; does not replace the product.",
                "recommended": recommended == "refund",
            },
            {
                "id": "reship",
                "label": "Priority replacement",
                "estimatedCost": financial["replacementCostEstimate"],
                "resolutionDays": 3
                if inventory["availableUnits"] > 0
                else inventory["replenishmentDays"] + 3,
                "relationshipRecovery": "High",
                "feasible": inventory["availableUnits"] > 0,
                "conditions": (
                    f"{inventory['availableUnits']} assumed replacement unit(s) available."
                )
                if inventory["availableUnits"] > 0
                else f"Wait {inventory['replenishmentDays']} assumed replenishment days.",
                "risk": "Another fulfilment failure would further damage the relationship.",
                "recommended": recommended == "reship",
            },
            {
                "id": "credit",
                "label": "Service credit",
                "estimatedCost": financial["serviceCreditEstimate"],
                "resolutionDays": 1,
                "relationshipRecovery": "Low" if ticket["lateDays"] >= 30 else "Medium",
                "feasible": True,
                "conditions": "Requires customer acceptance and a valid future purchase channel.",
                "risk": "May be inadequate for a severe delay or one-star review.",
                "recommended": False,
            },
            {
                "id": "monitor",
                "label": "Explain and monitor",
                "estimatedCost": 0,
                "resolutionDays": 7,
                "relationshipRecovery": "Low",
                "feasible": True,
                "conditions": "Provide a fact-based update and monitor the case.",
                "risk": "Low financial cost but high relationship risk for severe complaints.",
                "recommended": False,
            },
        ]

    def investigate(self, complaint_id: str) -> dict[str, Any]:
        ticket = self.complaint(complaint_id)
        options = self.resolution_options(complaint_id)
        recommendation = next(option for option in options if option["recommended"])
        return {
            "complaintId": ticket["id"],
            "customerId": ticket["customerId"],
            "priority": f"{ticket['priorityLevel']}/{ticket['priorityScore']}",
            "timeline": self.order_timeline(complaint_id),
            "inventory": self.inventory_availability(complaint_id),
            "financial": self.financial_impact(complaint_id),
            "options": options,
            "recommendation": recommendation,
            "rationale": (
                "A one-star review with an extreme delivery delay makes a fast "
                "refund the strongest recovery option under the demo policy."
            )
            if recommendation["id"] == "refund"
            else (
                "A replacement is available and can resolve the fulfilment "
                "failure at lower estimated cost than a full refund."
            ),
            "boundary": (
                "Order, review and delivery dates are Olist facts. Ticket SLA is "
                "CRM replay. Inventory and financial impacts are labelled demo "
                "assumptions."
            ),
        }

    def draft_reply(self, complaint_id: str, tone: str) -> dict[str, Any]:
        ticket = self.complaint(complaint_id)
        prefix = (
            "Hello, we are sorry that this experience has taken so long to resolve."
            if tone == "empathetic"
            else "Hello, we have received your service request."
        )
        return {
            "complaintId": ticket["id"],
            "status": "Unsent draft",
            "draft": (
                f"{prefix} We are reviewing order {ticket['orderId']}, including "
                "its delivery timeline. A team member will verify the proposed "
                "resolution before confirming the next step."
            ),
            "verifiedFacts": {
                key: ticket[key]
                for key in (
                    "id",
                    "customerId",
                    "orderId",
                    "issue",
                    "priorityScore",
                    "priorityLevel",
                    "reasons",
                    "nextAction",
                )
            },
        }
