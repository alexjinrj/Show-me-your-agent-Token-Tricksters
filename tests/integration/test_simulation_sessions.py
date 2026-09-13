from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from business_coordinator.persistence.models import (
    AccountingImpactRow,
    BusinessEventRow,
    SimulationRunRow,
)
from business_coordinator.persistence.service import ActualStateService, commit_demo_files
from business_coordinator.simulation import SimulationService, warehouse_capacity_increase

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


def test_ingestion_snapshot_fork_and_persisted_run_end_to_end(
    service: ActualStateService, demo_path: Path
) -> None:
    commit_demo_files(service, ((kind, demo_path / f"{kind}.csv") for kind in ORDER))
    actual_hash = service.actual_state_hash()
    manifest = service.create_snapshot(datetime.fromisoformat("2026-09-12T23:59:00+08:00"))
    bundle = service.load_snapshot(manifest.snapshot_id)
    simulations = SimulationService(service.engine)
    parent = simulations.create_session(manifest.snapshot_id, "Baseline")
    child = simulations.fork_session(parent.simulation_session_id, "Warehouse +1")
    simulations.add_event(child.simulation_session_id, warehouse_capacity_increase())
    assert simulations.get_session(parent.simulation_session_id).scenario_events == ()
    assert len(simulations.get_session(child.simulation_session_id).scenario_events) == 1

    baseline = simulations.run_session(
        parent.simulation_session_id, bundle, horizon_days=30, random_seed=42
    )
    alternative = simulations.run_session(
        child.simulation_session_id, bundle, horizon_days=30, random_seed=42
    )
    comparison = simulations.compare_runs(baseline, alternative)
    assert comparison["average_waiting_hours"]["difference"] < 0
    assert service.actual_state_hash() == actual_hash
    with Session(service.engine) as database:
        assert database.scalar(select(func.count()).select_from(SimulationRunRow)) == 2
        assert (database.scalar(select(func.count()).select_from(AccountingImpactRow)) or 0) > 0
        assert database.scalar(select(func.count()).select_from(BusinessEventRow)) == 596
