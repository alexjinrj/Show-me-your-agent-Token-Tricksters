from __future__ import annotations

import csv
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from business_coordinator.domain.models import (
    ScenarioEvent,
    SimulationRunResult,
)
from business_coordinator.inventory.demand import (
    calculate_demand_shortages,
    create_demand_aligned_events,
)
from business_coordinator.inventory.recommendation import (
    select_recommended_strategy,
)
from business_coordinator.inventory.reorder import (
    read_csv,
)
from business_coordinator.persistence.database import (
    create_schema,
    make_engine,
    sqlite_url,
)
from business_coordinator.persistence.service import (
    ActualStateService,
    commit_demo_files,
)
from business_coordinator.simulation import (
    run_simulation,
)

DATABASE_PATH = "actual_state.db"
DATA_DIR = Path("data/demo/raw")

RECOMMENDATION_PATH = Path("data/demo/expected/reorder_recommendations.csv")
COMPARISON_PATH = Path("data/demo/expected/strategy_comparison.csv")
RUN_MANIFEST_PATH = Path("data/demo/expected/strategy_runs.csv")
FINAL_RECOMMENDATION_PATH = Path("data/demo/expected/final_recommendation.json")

INGESTION_ORDER = (
    "customers",
    "suppliers",
    "items",
    "inventory",
    "sales_orders",
    "purchase_orders",
    "resources",
    "opening_balances",
)

METRICS = (
    "ending_backlog",
    "fulfilment_rate",
    "stockout_count",
    "ending_inventory_quantity",
    "ending_inventory_value",
    "revenue",
    "cost_of_goods_sold",
    "gross_profit",
    "accounts_payable",
    "ending_cash",
    "minimum_cash",
)


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
            ScenarioEvent(
                event_type="inventory_replenishment",
                effective_day=Decimal("3"),
                payload={
                    "sku": row["sku"],
                    "quantity": str(quantity),
                    "order_number": (f"{strategy.upper()}-{row['sku']}"),
                },
            )
        )

    return events


def total_replenishment_quantity(
    events: list[ScenarioEvent],
) -> Decimal:
    return sum(
        (Decimal(str(event.payload["quantity"])) for event in events),
        Decimal("0"),
    )


def write_strategy_comparison(
    runs: dict[str, SimulationRunResult],
) -> None:
    COMPARISON_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    strategy_names = list(runs)

    with COMPARISON_PATH.open(
        mode="w",
        encoding="utf-8",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "metric",
                *strategy_names,
            ],
        )
        writer.writeheader()

        for metric in METRICS:
            row = {"metric": metric}

            for strategy, result in runs.items():
                value = getattr(
                    result.summary_metrics,
                    metric,
                )
                row[strategy] = str(value)

            writer.writerow(row)


def write_run_manifest(
    runs: dict[str, SimulationRunResult],
    events_by_strategy: dict[
        str,
        list[ScenarioEvent],
    ],
) -> None:
    RUN_MANIFEST_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with RUN_MANIFEST_PATH.open(
        mode="w",
        encoding="utf-8",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "strategy",
                "simulation_run_id",
                "result_hash",
                "event_count",
                "replenishment_quantity",
            ],
        )
        writer.writeheader()

        for strategy, result in runs.items():
            events = events_by_strategy[strategy]

            writer.writerow(
                {
                    "strategy": strategy,
                    "simulation_run_id": (result.simulation_run_id),
                    "result_hash": result.result_hash,
                    "event_count": len(events),
                    "replenishment_quantity": (total_replenishment_quantity(events)),
                }
            )


def main() -> None:
    engine = make_engine(sqlite_url(DATABASE_PATH))
    create_schema(engine)

    service = ActualStateService(
        engine,
        source_system=("microsoft-adventureworks-demo"),
    )

    commit_demo_files(
        service,
        (
            (
                source_type,
                DATA_DIR / f"{source_type}.csv",
            )
            for source_type in INGESTION_ORDER
        ),
    )

    manifest = service.create_snapshot(datetime.fromisoformat("2026-09-12T23:59:00+08:00"))
    snapshot = service.load_snapshot(manifest.snapshot_id)

    recommendations = read_csv(RECOMMENDATION_PATH)

    inventory_rows = read_csv(DATA_DIR / "inventory.csv")
    sales_rows = read_csv(DATA_DIR / "sales_orders.csv")
    purchase_rows = read_csv(DATA_DIR / "purchase_orders.csv")

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
                recommendations,
                "critical_only",
            )
        ),
        "demand_aligned": (create_demand_aligned_events(demand_shortages)),
        "full": create_replenishment_events(
            recommendations,
            "full",
        ),
    }

    print("Demand-aligned shortages:")

    for sku, quantity in sorted(demand_shortages.items()):
        print(f"{sku}: shortage={quantity}")

    actual_state_before = service.actual_state_hash()

    runs = {
        strategy: run_simulation(
            snapshot,
            events,
            30,
            42,
        )
        for strategy, events in events_by_strategy.items()
    }

    actual_state_after = service.actual_state_hash()

    actual_state_unchanged = actual_state_before == actual_state_after

    if not actual_state_unchanged:
        raise RuntimeError("Simulation modified Actual State")

    write_strategy_comparison(runs)

    write_run_manifest(
        runs,
        events_by_strategy,
    )

    recommendation = select_recommended_strategy(
        {strategy: (result.summary_metrics) for strategy, result in runs.items()},
        {strategy: (result.simulation_run_id) for strategy, result in runs.items()},
        {
            strategy: (total_replenishment_quantity(events))
            for strategy, events in events_by_strategy.items()
        },
        actual_state_unchanged=(actual_state_unchanged),
    )

    FINAL_RECOMMENDATION_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    FINAL_RECOMMENDATION_PATH.write_text(
        recommendation.model_dump_json(indent=2),
        encoding="utf-8",
    )

    for strategy, result in runs.items():
        events = events_by_strategy[strategy]

        print()
        print(f"Strategy: {strategy}")
        print(
            "Run ID:",
            result.simulation_run_id,
        )
        print(f"Events: {len(events)}")
        print(
            "Replenishment quantity:",
            total_replenishment_quantity(events),
        )

        for metric in METRICS:
            value = getattr(
                result.summary_metrics,
                metric,
            )
            print(f"{metric}: {value}")

    print()
    print(
        "Actual State unchanged:",
        str(actual_state_unchanged).lower(),
    )
    print(
        "Comparison saved to:",
        COMPARISON_PATH,
    )
    print(
        "Run manifest saved to:",
        RUN_MANIFEST_PATH,
    )

    print()
    print(
        "Recommended strategy:",
        recommendation.recommended_strategy,
    )
    print(
        "Selection method:",
        recommendation.selection_method,
    )
    print(
        "Final recommendation saved to:",
        FINAL_RECOMMENDATION_PATH,
    )


if __name__ == "__main__":
    main()
