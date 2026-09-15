from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from business_coordinator.domain.models import (
    ScenarioEvent,
    SimulationMetrics,
    SimulationRunResult,
    SnapshotBundle,
)
from business_coordinator.inventory.demand import (
    calculate_demand_shortages,
    create_demand_aligned_events,
)
from business_coordinator.inventory.recommendation import (
    StrategyRecommendation,
    select_recommended_strategy,
)
from business_coordinator.inventory.reorder import (
    build_reorder_recommendations,
)
from business_coordinator.simulation import (
    inventory_replenishment,
    run_simulation,
)


class StrategyRunSummary(BaseModel):
    """Auditable summary of one strategy run."""

    model_config = ConfigDict(frozen=True)

    strategy: str
    simulation_run_id: str
    result_hash: str
    event_count: int
    replenishment_quantity: Decimal
    metrics: SimulationMetrics


class InventoryStrategyToolResult(BaseModel):
    """Typed result returned to an Agent."""

    model_config = ConfigDict(frozen=True)

    recommendation: StrategyRecommendation
    demand_shortages: dict[str, Decimal]
    reorder_recommendations: tuple[
        dict[str, str],
        ...,
    ]
    strategy_runs: tuple[
        StrategyRunSummary,
        ...,
    ]


def include_recommendation(
    row: dict[str, str],
    strategy: str,
) -> bool:
    if row["needs_reorder"] != "true":
        return False

    if strategy == "critical_only":
        return row["risk_level"] == "critical"

    if strategy == "full":
        return True

    raise ValueError(f"unknown strategy: {strategy}")


def create_replenishment_events(
    recommendations: list[dict[str, str]],
    strategy: str,
    *,
    effective_day: Decimal = Decimal("3"),
) -> list[ScenarioEvent]:
    events: list[ScenarioEvent] = []

    for row in recommendations:
        if not include_recommendation(
            row,
            strategy,
        ):
            continue

        quantity = Decimal(row["recommended_quantity"])

        if quantity <= 0:
            continue

        events.append(
            inventory_replenishment(
                row["sku"],
                quantity,
                effective_day=effective_day,
            )
        )

    return events


def total_replenishment_quantity(
    events: list[ScenarioEvent],
) -> Decimal:
    return sum(
        (
            Decimal(str(event.payload["quantity"]))
            for event in events
            if event.event_type == "inventory_replenishment"
        ),
        Decimal("0"),
    )


def run_inventory_strategy_analysis(
    snapshot: SnapshotBundle,
    item_rows: list[dict[str, str]],
    inventory_rows: list[dict[str, str]],
    sales_rows: list[dict[str, str]],
    purchase_rows: list[dict[str, str]],
    *,
    horizon_days: int = 30,
    random_seed: int = 42,
    effective_day: Decimal = Decimal("3"),
) -> InventoryStrategyToolResult:
    """
    Run deterministic inventory strategies
    against a detached snapshot.
    """

    reorder_recommendations = build_reorder_recommendations(
        item_rows,
        inventory_rows,
    )

    demand_shortages = calculate_demand_shortages(
        inventory_rows,
        sales_rows,
        purchase_rows,
    )

    events_by_strategy: dict[
        str,
        list[ScenarioEvent],
    ] = {
        "baseline": [],
        "critical_only": (
            create_replenishment_events(
                reorder_recommendations,
                "critical_only",
                effective_day=effective_day,
            )
        ),
        "demand_aligned": (
            create_demand_aligned_events(
                demand_shortages,
                effective_day=effective_day,
            )
        ),
        "full": create_replenishment_events(
            reorder_recommendations,
            "full",
            effective_day=effective_day,
        ),
    }

    runs: dict[
        str,
        SimulationRunResult,
    ] = {
        strategy: run_simulation(
            snapshot,
            events,
            horizon_days,
            random_seed,
        )
        for strategy, events in events_by_strategy.items()
    }

    replenishment_quantities = {
        strategy: total_replenishment_quantity(events)
        for strategy, events in events_by_strategy.items()
    }

    recommendation = select_recommended_strategy(
        {strategy: result.summary_metrics for strategy, result in runs.items()},
        {strategy: (result.simulation_run_id) for strategy, result in runs.items()},
        replenishment_quantities,
        actual_state_unchanged=True,
    )

    strategy_runs = tuple(
        StrategyRunSummary(
            strategy=strategy,
            simulation_run_id=(result.simulation_run_id),
            result_hash=result.result_hash,
            event_count=len(events_by_strategy[strategy]),
            replenishment_quantity=(replenishment_quantities[strategy]),
            metrics=result.summary_metrics,
        )
        for strategy, result in runs.items()
    )

    return InventoryStrategyToolResult(
        recommendation=recommendation,
        demand_shortages=demand_shortages,
        reorder_recommendations=tuple(reorder_recommendations),
        strategy_runs=strategy_runs,
    )
