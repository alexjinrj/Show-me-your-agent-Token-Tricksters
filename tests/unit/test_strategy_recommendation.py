from decimal import Decimal

from business_coordinator.domain.models import (
    SimulationMetrics,
)
from business_coordinator.inventory.recommendation import (
    select_recommended_strategy,
)


def metrics(
    *,
    backlog: int,
    fulfilment: str,
    gross_profit: str,
    cash: str,
) -> SimulationMetrics:
    return SimulationMetrics(
        ending_backlog=backlog,
        fulfilment_rate=Decimal(fulfilment),
        gross_profit=Decimal(gross_profit),
        ending_cash=Decimal(cash),
    )


def test_selects_dominant_demand_strategy() -> None:
    strategy_metrics = {
        "baseline": metrics(
            backlog=43,
            fulfilment="0.57",
            gross_profit="176.15",
            cash="-54236.53",
        ),
        "critical_only": metrics(
            backlog=43,
            fulfilment="0.57",
            gross_profit="176.15",
            cash="-54810.20",
        ),
        "demand_aligned": metrics(
            backlog=0,
            fulfilment="1.00",
            gross_profit="301.86",
            cash="-54110.66",
        ),
        "full": metrics(
            backlog=33,
            fulfilment="0.67",
            gross_profit="198.90",
            cash="-55942.65",
        ),
    }

    run_ids = {strategy: f"{strategy}-run" for strategy in strategy_metrics}

    recommendation = select_recommended_strategy(
        strategy_metrics,
        run_ids,
        {
            "baseline": Decimal("0"),
            "critical_only": Decimal("18"),
            "demand_aligned": Decimal("43"),
            "full": Decimal("647"),
        },
        actual_state_unchanged=True,
    )

    assert recommendation.recommended_strategy == "demand_aligned"
    assert recommendation.selection_method == "pareto_dominance"
    assert recommendation.backlog_reduction == 43
    assert recommendation.fulfilment_improvement == Decimal("0.43")
    assert recommendation.gross_profit_improvement == Decimal("125.71")
    assert recommendation.cash_improvement == Decimal("125.87")


def test_can_recommend_baseline() -> None:
    strategy_metrics = {
        "baseline": metrics(
            backlog=0,
            fulfilment="1",
            gross_profit="100",
            cash="100",
        ),
        "expensive_option": metrics(
            backlog=1,
            fulfilment="0.90",
            gross_profit="90",
            cash="50",
        ),
    }

    recommendation = select_recommended_strategy(
        strategy_metrics,
        {
            "baseline": "baseline-run",
            "expensive_option": ("expensive-run"),
        },
        {
            "baseline": Decimal("0"),
            "expensive_option": Decimal("10"),
        },
        actual_state_unchanged=True,
    )

    assert recommendation.recommended_strategy == "baseline"
