from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from business_coordinator.inventory.recommendation import (
    StrategyRecommendation,
)
from business_coordinator.tools.inventory import (
    get_inventory_recommendation,
)


class InventoryAgentResponse(BaseModel):
    """Structured response produced for inventory users."""

    model_config = ConfigDict(frozen=True)

    recommendation: str
    operational_impact: str
    financial_impact: str
    selection_method: str
    baseline_run_id: str
    recommended_run_id: str
    actual_state_unchanged: bool
    assumptions: tuple[str, ...]
    limitations: tuple[str, ...]


def build_inventory_agent_response(
    recommendation: StrategyRecommendation | None = None,
) -> InventoryAgentResponse:
    result = recommendation if recommendation is not None else get_inventory_recommendation()

    strategy_name = result.recommended_strategy.replace(
        "_",
        " ",
    )
    fulfilment_points = result.fulfilment_improvement * Decimal("100")

    return InventoryAgentResponse(
        recommendation=(
            f"Use the {strategy_name} strategy and replenish {result.replenishment_quantity} units."
        ),
        operational_impact=(
            "Expected backlog reduction: "
            f"{result.backlog_reduction}; "
            "fulfilment improvement: "
            f"{fulfilment_points:.2f} "
            "percentage points."
        ),
        financial_impact=(
            "Expected gross profit improvement: "
            f"{result.gross_profit_improvement}; "
            "expected cash improvement: "
            f"{result.cash_improvement}."
        ),
        selection_method=result.selection_method,
        baseline_run_id=result.baseline_run_id,
        recommended_run_id=(result.recommended_run_id),
        actual_state_unchanged=(result.actual_state_unchanged),
        assumptions=result.assumptions,
        limitations=result.limitations,
    )
