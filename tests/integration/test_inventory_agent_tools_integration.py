from datetime import datetime
from decimal import Decimal
from pathlib import Path

from enterprise_state.service import (
    ActualStateService,
    commit_demo_files,
)
from tools.inventory import InventoryAgentTools

ORDER = (
    "customers",
    "suppliers",
    "items",
    "inventory",
    "sales_orders",
    "purchase_orders",
    "resources",
    "opening_balances",
)


def test_inventory_tools_from_actual_state_through_strategy(
    service: ActualStateService,
    demo_path: Path,
) -> None:
    commit_demo_files(
        service,
        (
            (
                source_type,
                demo_path / f"{source_type}.csv",
            )
            for source_type in ORDER
        ),
    )

    actual_hash_before = service.actual_state_hash()

    manifest = service.create_snapshot(datetime.fromisoformat("2026-09-12T23:59:00+08:00"))

    tools = InventoryAgentTools(service.engine)

    reorder_result = tools.call(
        "list_inventory_reorder_candidates",
        {
            "snapshot_id": manifest.snapshot_id,
            "risk_level": "all",
            "top_n": 10,
        },
    )

    assert reorder_result["snapshot_id"] == manifest.snapshot_id
    assert reorder_result["snapshot_hash"] == manifest.content_hash
    assert reorder_result["state_type"] == "actual"
    assert reorder_result["candidate_count"] == 6
    assert Decimal(
        reorder_result["total_recommended_quantity"]
    ) == Decimal("647")

    reorder_skus = {row["sku"] for row in reorder_result["candidates"]}

    assert reorder_skus == {
        "WB-H098",
        "PK-7098",
        "TT-M928",
        "GL-H102-M",
        "RA-H123",
        "SJ-0194-M",
    }

    critical_result = tools.call(
        "list_inventory_reorder_candidates",
        {
            "snapshot_id": manifest.snapshot_id,
            "risk_level": "critical",
            "top_n": 10,
        },
    )

    assert critical_result["candidate_count"] == 3
    assert {row["sku"] for row in critical_result["candidates"]} == {
        "GL-H102-M",
        "RA-H123",
        "SJ-0194-M",
    }

    strategy_result = tools.call(
        "compare_inventory_replenishment_strategies",
        {
            "snapshot_id": manifest.snapshot_id,
            "horizon_days": 30,
            "random_seed": 42,
            "effective_day": "3",
        },
    )

    assert strategy_result["snapshot_id"] == manifest.snapshot_id
    assert strategy_result["snapshot_hash"] == manifest.content_hash
    assert strategy_result["state_type"] == "simulated"

    demand_shortages = {
        sku: Decimal(quantity) for sku, quantity in strategy_result["demand_shortages"].items()
    }

    assert demand_shortages == {
        "PK-7098": Decimal("5"),
        "WB-H098": Decimal("38"),
    }

    strategy_names = {row["strategy"] for row in strategy_result["strategy_runs"]}

    assert strategy_names == {
        "baseline",
        "critical_only",
        "demand_aligned",
        "full",
    }

    recommendation = strategy_result["recommendation"]

    assert recommendation["recommended_strategy"] in strategy_names
    assert recommendation["actual_state_unchanged"] is True
    assert recommendation["baseline_run_id"]
    assert recommendation["recommended_run_id"]

    assert service.actual_state_hash() == actual_hash_before
