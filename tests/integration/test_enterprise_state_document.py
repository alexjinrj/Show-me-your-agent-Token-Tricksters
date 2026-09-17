from __future__ import annotations

from datetime import datetime
from pathlib import Path

from core.simulation import run_simulation
from enterprise_state.service import ActualStateService, commit_demo_files

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


def test_actual_enterprise_state_is_queryable_and_directly_simulatable(
    service: ActualStateService, demo_path: Path
) -> None:
    commit_demo_files(service, ((kind, demo_path / f"{kind}.csv") for kind in ORDER))
    as_of = datetime.fromisoformat("2026-09-12T23:59:00+08:00")

    state = service.get_enterprise_state(as_of)
    detached = state.snapshot(
        object_types={
            "sales_order",
            "purchase_order",
            "item",
            "inventory_position",
            "resource_capacity",
            "balance",
        }
    )

    assert state.state_type == "actual"
    assert state.objects("sales_order")
    assert state.objects("inventory_position")
    assert detached is not state
    assert detached.records is not state.records

    result = run_simulation(state, [], 1, 42)
    assert result.status == "completed"
    assert result.horizon_days == 1
