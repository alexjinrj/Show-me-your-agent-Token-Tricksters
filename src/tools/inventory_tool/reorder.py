from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

RiskLevel = Literal[
    "critical",
    "high",
    "medium",
    "low",
]


class ReorderCandidate(BaseModel):
    """One typed inventory reorder recommendation."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    sku: str
    name: str
    current_stock: Decimal
    reorder_point: Decimal
    target_stock: Decimal
    needs_reorder: bool
    risk_level: RiskLevel
    recommended_quantity: Decimal


def build_reorder_recommendations(
    items: list[dict[str, str]],
    inventory: list[dict[str, str]],
) -> list[ReorderCandidate]:
    """Build deterministic reorder recommendations."""

    inventory_by_sku: dict[str, Decimal] = defaultdict(
        lambda: Decimal("0")
    )

    for row in inventory:
        inventory_by_sku[row["sku"]] += Decimal(
            row["quantity"]
        )

    results: list[ReorderCandidate] = []

    for item in items:
        sku = item["sku"]
        current_stock = inventory_by_sku[sku]
        reorder_point = Decimal(
            item["reorder_point"]
        )

        needs_reorder = (
            current_stock <= reorder_point
        )

        target_stock = (
            reorder_point * Decimal("2")
        )

        recommended_quantity = max(
            Decimal("0"),
            target_stock - current_stock,
        )

        risk_level: RiskLevel

        if current_stock <= 0:
            risk_level = "critical"
        elif (
            current_stock
            <= reorder_point / Decimal("2")
        ):
            risk_level = "high"
        elif current_stock <= reorder_point:
            risk_level = "medium"
        else:
            risk_level = "low"

        results.append(
            ReorderCandidate(
                sku=sku,
                name=item["name"],
                current_stock=current_stock,
                reorder_point=reorder_point,
                target_stock=target_stock,
                needs_reorder=needs_reorder,
                risk_level=risk_level,
                recommended_quantity=(
                    recommended_quantity
                ),
            )
        )

    return results