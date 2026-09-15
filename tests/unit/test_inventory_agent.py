from decimal import Decimal

import pytest

import business_coordinator.agent.inventory_agent as agent
from business_coordinator.inventory.recommendation import (
    StrategyRecommendation,
)


def example_recommendation() -> StrategyRecommendation:
    return StrategyRecommendation(
        recommended_strategy="demand_aligned",
        selection_method="pareto_dominance",
        baseline_run_id="baseline-run",
        recommended_run_id="recommended-run",
        replenishment_quantity=Decimal("43"),
        backlog_reduction=43,
        fulfilment_improvement=Decimal("0.4300"),
        gross_profit_improvement=Decimal("125.71"),
        cash_improvement=Decimal("125.87"),
        actual_state_unchanged=True,
        assumptions=("Active orders represent demand.",),
        limitations=("Demo data only.",),
    )


def test_builds_inventory_agent_response() -> None:
    response = agent.build_inventory_agent_response(example_recommendation())

    assert response.recommendation == ("Use the demand aligned strategy and replenish 43 units.")
    assert response.operational_impact == (
        "Expected backlog reduction: 43; fulfilment improvement: 43.00 percentage points."
    )
    assert response.financial_impact == (
        "Expected gross profit improvement: 125.71; expected cash improvement: 125.87."
    )
    assert response.selection_method == "pareto_dominance"
    assert response.baseline_run_id == "baseline-run"
    assert response.recommended_run_id == "recommended-run"
    assert response.actual_state_unchanged is True


def test_uses_typed_inventory_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = example_recommendation()

    monkeypatch.setattr(
        agent,
        "get_inventory_recommendation",
        lambda: expected,
    )

    response = agent.build_inventory_agent_response()

    assert response.assumptions == ("Active orders represent demand.",)
    assert response.limitations == ("Demo data only.",)
