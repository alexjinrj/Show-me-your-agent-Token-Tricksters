from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from business_coordinator.domain.models import (
    SimulationMetrics,
)

SelectionMethod = Literal[
    "pareto_dominance",
    "ordered_fallback",
]


class StrategyRecommendation(BaseModel):
    model_config = ConfigDict(frozen=True)

    recommended_strategy: str
    selection_method: SelectionMethod

    baseline_run_id: str
    recommended_run_id: str

    replenishment_quantity: Decimal
    backlog_reduction: int
    fulfilment_improvement: Decimal
    gross_profit_improvement: Decimal
    cash_improvement: Decimal

    actual_state_unchanged: bool
    assumptions: tuple[str, ...]
    limitations: tuple[str, ...]


def dominates(
    candidate: SimulationMetrics,
    other: SimulationMetrics,
) -> bool:
    not_worse = (
        candidate.ending_backlog
        <= other.ending_backlog
        and candidate.fulfilment_rate
        >= other.fulfilment_rate
        and candidate.gross_profit
        >= other.gross_profit
        and candidate.ending_cash
        >= other.ending_cash
    )

    strictly_better = (
        candidate.ending_backlog
        < other.ending_backlog
        or candidate.fulfilment_rate
        > other.fulfilment_rate
        or candidate.gross_profit
        > other.gross_profit
        or candidate.ending_cash
        > other.ending_cash
    )

    return not_worse and strictly_better


def select_recommended_strategy(
    metrics_by_strategy: dict[
        str,
        SimulationMetrics,
    ],
    run_ids: dict[str, str],
    replenishment_quantities: dict[
        str,
        Decimal,
    ],
    *,
    actual_state_unchanged: bool,
) -> StrategyRecommendation:
    if "baseline" not in metrics_by_strategy:
        raise ValueError(
            "baseline strategy is required"
        )

    if set(metrics_by_strategy) != set(run_ids):
        raise ValueError(
            "strategy metrics and run IDs "
            "must have matching keys"
        )

    dominant_strategies = [
        candidate_name
        for candidate_name, candidate
        in metrics_by_strategy.items()
        if all(
            other_name == candidate_name
            or dominates(candidate, other)
            for other_name, other
            in metrics_by_strategy.items()
        )
    ]

    if len(dominant_strategies) == 1:
        selected_name = dominant_strategies[0]
        selection_method: SelectionMethod = (
            "pareto_dominance"
        )
    else:
        def ranking(
            strategy_name: str,
        ) -> tuple[
            int,
            Decimal,
            Decimal,
            Decimal,
            str,
        ]:
            metrics = metrics_by_strategy[
                strategy_name
            ]

            return (
                metrics.ending_backlog,
                -metrics.fulfilment_rate,
                -metrics.ending_cash,
                -metrics.gross_profit,
                strategy_name,
            )

        selected_name = min(
            metrics_by_strategy,
            key=ranking,
        )
        selection_method = "ordered_fallback"

    baseline = metrics_by_strategy["baseline"]
    selected = metrics_by_strategy[selected_name]

    return StrategyRecommendation(
        recommended_strategy=selected_name,
        selection_method=selection_method,
        baseline_run_id=run_ids["baseline"],
        recommended_run_id=run_ids[
            selected_name
        ],
        replenishment_quantity=(
            replenishment_quantities.get(
                selected_name,
                Decimal("0"),
            )
        ),
        backlog_reduction=(
            baseline.ending_backlog
            - selected.ending_backlog
        ),
        fulfilment_improvement=(
            selected.fulfilment_rate
            - baseline.fulfilment_rate
        ),
        gross_profit_improvement=(
            selected.gross_profit
            - baseline.gross_profit
        ),
        cash_improvement=(
            selected.ending_cash
            - baseline.ending_cash
        ),
        actual_state_unchanged=(
            actual_state_unchanged
        ),
        assumptions=(
            "Open and backlog sales orders "
            "represent active demand.",
            "Open purchase orders represent "
            "incoming supply.",
            "Replenishment arrives on the "
            "configured effective day.",
        ),
        limitations=(
            "Stockout count records the first "
            "shortage encounter.",
            "Results depend on the configured "
            "simulation horizon.",
            "The recommendation uses the "
            "available demo data.",
        ),
    )