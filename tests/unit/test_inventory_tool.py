from decimal import Decimal
from pathlib import Path

import pytest

from business_coordinator.inventory.recommendation import (
    StrategyRecommendation,
)
from business_coordinator.tools.inventory import (
    get_inventory_recommendation,
)


def example_recommendation() -> StrategyRecommendation:
    return StrategyRecommendation(
        recommended_strategy="demand_aligned",
        selection_method="pareto_dominance",
        baseline_run_id="baseline-run",
        recommended_run_id="recommended-run",
        replenishment_quantity=Decimal("43"),
        backlog_reduction=43,
        fulfilment_improvement=Decimal("0.43"),
        gross_profit_improvement=Decimal("125.71"),
        cash_improvement=Decimal("125.87"),
        actual_state_unchanged=True,
        assumptions=("Active orders represent demand.",),
        limitations=("Demo data only.",),
    )


def test_loads_typed_inventory_recommendation(
    tmp_path: Path,
) -> None:
    expected = example_recommendation()
    path = tmp_path / "recommendation.json"

    path.write_text(
        expected.model_dump_json(indent=2),
        encoding="utf-8",
    )

    actual = get_inventory_recommendation(path)

    assert actual == expected
    assert actual.recommended_strategy == "demand_aligned"
    assert actual.replenishment_quantity == Decimal("43")


def test_missing_recommendation_raises_error(
    tmp_path: Path,
) -> None:
    missing_path = tmp_path / "missing.json"

    with pytest.raises(
        FileNotFoundError,
        match="does not exist",
    ):
        get_inventory_recommendation(missing_path)


def test_invalid_recommendation_raises_error(
    tmp_path: Path,
) -> None:
    path = tmp_path / "invalid.json"

    path.write_text(
        "{}",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="recommendation is invalid",
    ):
        get_inventory_recommendation(path)
