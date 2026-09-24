from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

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

def test_reorder_candidates_with_replenished_stock(
    service: ActualStateService,
) -> None:
    scenario_path = (
        Path(__file__).resolve().parents[2]
        / "data"
        / "load_data"
        / "inventory_replenishment_test"
    )

    commit_demo_files(
        service,
        (
            (
                source_type,
                scenario_path / f"{source_type}.csv",
            )
            for source_type in ORDER
        ),
    )

    manifest = service.create_snapshot(
        datetime.fromisoformat(
            "2026-09-12T23:59:00+08:00"
        )
    )

    tools = InventoryAgentTools(service.engine)

    reorder_result = tools.call(
        "list_inventory_reorder_candidates",
        {
            "snapshot_id": manifest.snapshot_id,
            "risk_level": "all",
            "top_n": 10,
        },
    )

    assert reorder_result["state_type"] == "actual"
    assert reorder_result["snapshot_id"] == manifest.snapshot_id
    assert reorder_result["snapshot_hash"] == manifest.content_hash

    assert reorder_result["candidate_count"] == 5
    assert Decimal(
        reorder_result["total_recommended_quantity"]
    ) == Decimal("642")

    reorder_skus = {
        row["sku"]
        for row in reorder_result["candidates"]
    }

    assert "WB-H098" not in reorder_skus

    assert reorder_skus == {
        "PK-7098",
        "TT-M928",
        "GL-H102-M",
        "RA-H123",
        "SJ-0194-M",
    }

@pytest.mark.parametrize(
    (
        "scenario_name",
        "expected_candidate_count",
        "expected_total",
        "checked_sku",
        "expected_present",
        "expected_quantity",
        "expected_risk",
    ),
    (
        (
            "inventory_replenishment_test",
            5,
            "642",
            "WB-H098",
            False,
            None,
            None,
        ),
        (
            "inventory_at_reorder_point_test",
            6,
            "645",
            "WB-H098",
            True,
            "3",
            "medium",
        ),
        (
            "inventory_out_of_stock_test",
            6,
            "648",
            "WB-H098",
            True,
            "6",
            "critical",
        ),
        (
            "inventory_tire_recovered_test",
            5,
            "28",
            "TT-M928",
            False,
            None,
            None,
        ),
        (
            "inventory_high_reorder_point_test",
            6,
            "661",
            "WB-H098",
            True,
            "19",
            "high",
        ),
    ),
)
def test_reorder_recommendations_with_different_data(
    service: ActualStateService,
    scenario_name: str,
    expected_candidate_count: int,
    expected_total: str,
    checked_sku: str,
    expected_present: bool,
    expected_quantity: str | None,
    expected_risk: str | None,
) -> None:
    repository_root = Path(__file__).resolve().parents[2]

    scenario_path = (
        repository_root
        / "data"
        / "load_data"
        / scenario_name
    )

    commit_demo_files(
        service,
        (
            (
                source_type,
                scenario_path / f"{source_type}.csv",
            )
            for source_type in ORDER
        ),
    )

    manifest = service.create_snapshot(
        datetime.fromisoformat(
            "2026-09-12T23:59:00+08:00"
        )
    )

    tools = InventoryAgentTools(service.engine)

    result = tools.call(
        "list_inventory_reorder_candidates",
        {
            "snapshot_id": manifest.snapshot_id,
            "risk_level": "all",
            "top_n": 20,
        },
    )

    assert result["state_type"] == "actual"
    assert result["snapshot_id"] == manifest.snapshot_id
    assert result["snapshot_hash"] == manifest.content_hash

    assert result["candidate_count"] == (
        expected_candidate_count
    )

    assert Decimal(
        result["total_recommended_quantity"]
    ) == Decimal(expected_total)

    candidates = {
        row["sku"]: row
        for row in result["candidates"]
    }

    if not expected_present:
        assert checked_sku not in candidates
        return

    assert checked_sku in candidates

    checked_candidate = candidates[checked_sku]

    assert Decimal(
        checked_candidate["recommended_quantity"]
    ) == Decimal(expected_quantity)

    assert checked_candidate["risk_level"] == expected_risk