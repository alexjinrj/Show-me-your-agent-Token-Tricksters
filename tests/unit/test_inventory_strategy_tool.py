from __future__ import annotations

from decimal import Decimal
from typing import cast

import pytest

import tools.inventory.strategy as tool
from core.models import (
    ScenarioEvent,
    SimulationMetrics,
    SimulationRunResult,
    SnapshotBundle,
)
from tools.inventory.reorder import (
    ReorderCandidate,
)
from tools.inventory.snapshot_adapter import (
    InventoryStrategyRows,
)


def reorder_candidate(
    sku: str,
    *,
    needs_reorder: bool,
    risk_level: str,
    recommended_quantity: str,
) -> ReorderCandidate:
    return ReorderCandidate.model_validate(
        {
            "sku": sku,
            "name": f"Item {sku}",
            "current_stock": "0",
            "reorder_point": "3",
            "target_stock": "6",
            "needs_reorder": needs_reorder,
            "risk_level": risk_level,
            "recommended_quantity": (
                recommended_quantity
            ),
        }
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


def simulation_result(
    number: int,
    summary: SimulationMetrics,
) -> SimulationRunResult:
    return SimulationRunResult(
        simulation_run_id=(f"00000000-0000-0000-0000-{number:012d}"),
        snapshot_hash="a" * 64,
        process_definition_hash="b" * 64,
        scenario_event_hash="c" * 64,
        horizon_days=30,
        random_seed=42,
        result_hash=f"{number:064x}",
        summary_metrics=summary,
        event_trace=(),
    )


def test_replenishment_strategy_filters_events() -> None:
    recommendations = [
        reorder_candidate(
            "SKU-A",
            needs_reorder=True,
            risk_level="critical",
            recommended_quantity="5",
        ),
        reorder_candidate(
            "SKU-B",
            needs_reorder=True,
            risk_level="medium",
            recommended_quantity="7",
        ),
        reorder_candidate(
            "SKU-C",
            needs_reorder=False,
            risk_level="low",
            recommended_quantity="0",
        ),
    ]

    critical = tool.create_replenishment_events(
        recommendations,
        "critical_only",
    )
    full = tool.create_replenishment_events(
        recommendations,
        "full",
    )

    assert tool.total_replenishment_quantity(critical) == Decimal("5")
    assert tool.total_replenishment_quantity(full) == Decimal("12")


def test_tool_runs_and_selects_best_strategy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recommendations = [
        reorder_candidate(
            "SKU-A",
            needs_reorder=True,
            risk_level="critical",
            recommended_quantity="5",
        ),
        reorder_candidate(
            "SKU-B",
            needs_reorder=True,
            risk_level="medium",
            recommended_quantity="7",
        ),
    ]

    monkeypatch.setattr(
        tool,
        "extract_inventory_strategy_rows",
        lambda _snapshot: InventoryStrategyRows(
            item_rows=(),
            inventory_rows=(),
            sales_rows=(),
            purchase_rows=(),
        ),
    )

    monkeypatch.setattr(
        tool,
        "build_reorder_recommendations",
        lambda _items, _inventory: recommendations,
    )
    monkeypatch.setattr(
        tool,
        "calculate_demand_shortages",
        lambda _inventory, _sales, _purchase: {"SKU-C": Decimal("10")},
    )

    run_results = iter(
        [
            simulation_result(
                1,
                metrics(
                    backlog=10,
                    fulfilment="0.50",
                    gross_profit="100",
                    cash="1000",
                ),
            ),
            simulation_result(
                2,
                metrics(
                    backlog=8,
                    fulfilment="0.60",
                    gross_profit="105",
                    cash="990",
                ),
            ),
            simulation_result(
                3,
                metrics(
                    backlog=0,
                    fulfilment="1.00",
                    gross_profit="150",
                    cash="1010",
                ),
            ),
            simulation_result(
                4,
                metrics(
                    backlog=2,
                    fulfilment="0.80",
                    gross_profit="120",
                    cash="900",
                ),
            ),
        ]
    )

    observed_quantities: list[Decimal] = []

    def fake_run_simulation(
        _snapshot: SnapshotBundle,
        events: list[ScenarioEvent],
        _horizon_days: int,
        _random_seed: int,
    ) -> SimulationRunResult:
        observed_quantities.append(tool.total_replenishment_quantity(events))
        return next(run_results)

    monkeypatch.setattr(
        tool,
        "run_simulation",
        fake_run_simulation,
    )

    result = tool.run_inventory_strategy_analysis(
        cast(SnapshotBundle, object()),
    )

    assert observed_quantities == [
        Decimal("0"),
        Decimal("5"),
        Decimal("10"),
        Decimal("12"),
    ]
    assert result.recommendation.recommended_strategy == "demand_aligned"
    assert result.recommendation.replenishment_quantity == Decimal("10")
    assert result.recommendation.selection_method == "pareto_dominance"
    assert len(result.strategy_runs) == 4
    assert result.demand_shortages == {"SKU-C": Decimal("10")}
