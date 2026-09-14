from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import yaml

from business_coordinator.domain.models import ScenarioEvent, SnapshotBundle
from business_coordinator.persistence.service import ActualStateService, commit_demo_files
from business_coordinator.simulation import (
    expedited_supplier_delivery,
    run_simulation,
    snapshot_to_state,
    warehouse_capacity_increase,
)

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


def snapshot(service: ActualStateService, demo_path: Path) -> SnapshotBundle:
    commit_demo_files(service, ((kind, demo_path / f"{kind}.csv") for kind in ORDER))
    manifest = service.create_snapshot(datetime.fromisoformat("2026-09-12T23:59:00+08:00"))
    return service.load_snapshot(manifest.snapshot_id)


def test_snapshot_adapter_is_deeply_isolated(service: ActualStateService, demo_path: Path) -> None:
    bundle = snapshot(service, demo_path)
    before = deepcopy(bundle.model_dump(mode="python"))
    state = snapshot_to_state(bundle)
    inventory = state.records_of_type("inventory_position")[0]
    cash = state.related("balance", "account_code", "CASH")
    state.update(inventory.record_id, "quantity_available", Decimal("0"))
    state.update(cash.record_id, "amount", Decimal("0"))
    assert bundle.model_dump(mode="python") == before


def test_snapshot_adapter_exposes_reusable_object_centric_state(
    service: ActualStateService, demo_path: Path
) -> None:
    state = snapshot_to_state(snapshot(service, demo_path))
    enterprise_state = state.enterprise_state(Decimal("0"))

    assert enterprise_state.state_type == "simulated"
    assert state.records_of_type("inventory_position")
    assert state.records_of_type("sales_order")
    assert all(record.record_kind == "object" for record in enterprise_state.records.values())


def test_reproducibility_and_actual_state_immutability(
    service: ActualStateService, demo_path: Path
) -> None:
    bundle = snapshot(service, demo_path)
    before = service.actual_state_hash()
    first = run_simulation(bundle, [], 30, 42)
    second = run_simulation(bundle, [], 30, 42)
    assert first.result_hash == second.result_hash
    assert first.event_trace == second.event_trace
    assert first.checkpoints == second.checkpoints
    assert [checkpoint.day for checkpoint in first.checkpoints] == list(range(31))
    assert first.checkpoints[-1].simulated_hour == Decimal("720")
    changed_kinds = {
        change.record_kind for checkpoint in first.checkpoints for change in checkpoint.changes
    }
    assert changed_kinds == {"object", "event", "activity_run"}
    assert any(checkpoint.new_event_record_ids for checkpoint in first.checkpoints)
    assert first.process_definition_versions == {"order_to_cash": 2, "procure_to_pay": 2}
    assert service.actual_state_hash() == before


def test_required_scenarios_are_deterministic_and_traceable(
    service: ActualStateService, demo_path: Path
) -> None:
    bundle = snapshot(service, demo_path)
    baseline = run_simulation(bundle, [], 30, 42)
    capacity = run_simulation(bundle, [warehouse_capacity_increase()], 30, 42)
    expedited = run_simulation(bundle, [expedited_supplier_delivery()], 30, 42)
    assert capacity.result_hash != baseline.result_hash
    assert (
        capacity.summary_metrics.average_waiting_hours
        < baseline.summary_metrics.average_waiting_hours
    )
    assert expedited.result_hash != baseline.result_hash
    assert any(event.event_type == "supplier_delivery_adjusted" for event in expedited.event_trace)


def test_order_arrival_uses_shared_inventory_and_resources(
    service: ActualStateService, demo_path: Path
) -> None:
    bundle = snapshot(service, demo_path)
    event = ScenarioEvent(
        event_type="order_arrival",
        effective_day=Decimal("1"),
        payload={"sku": "TT-R982", "quantity": "2", "order_number": "WHAT-IF-1"},
    )
    result = run_simulation(bundle, [event], 30, 7)
    assert any(
        item.event_type == "order_entered_simulation"
        and item.simulated_hour == Decimal("24")
        and item.details.get("sku") == "TT-R982"
        for item in result.event_trace
    )
    assert any(
        item.event_type == "customer_invoiced" and item.details.get("amount") == "7.98"
        for item in result.event_trace
    )


def test_every_accounting_impact_balances(service: ActualStateService, demo_path: Path) -> None:
    result = run_simulation(snapshot(service, demo_path), [], 30, 42)
    assert result.accounting_impacts
    for impact in result.accounting_impacts:
        assert sum(line.debit for line in impact.lines) == sum(line.credit for line in impact.lines)


def test_process_parameter_changes_runtime_without_python_business_logic_changes(
    service: ActualStateService, demo_path: Path, tmp_path: Path
) -> None:
    bundle = snapshot(service, demo_path)
    event = ScenarioEvent(
        event_type="order_arrival",
        effective_day=Decimal("1"),
        payload={"sku": "TT-R982", "quantity": "1", "order_number": "YAML-DRIVEN"},
    )
    source = Path(__file__).parents[2] / "config" / "processes"
    for name in ("order_to_cash.yaml", "procure_to_pay.yaml"):
        (tmp_path / name).write_text((source / name).read_text(encoding="utf-8"), encoding="utf-8")
    raw = yaml.safe_load((tmp_path / "order_to_cash.yaml").read_text(encoding="utf-8"))
    raw["parameters"]["customer_payment_delay_hours"] = 24
    (tmp_path / "order_to_cash.yaml").write_text(
        yaml.safe_dump(raw, sort_keys=False), encoding="utf-8"
    )

    baseline = run_simulation(bundle, [event], 30, 42)
    configured = run_simulation(bundle, [event], 30, 42, config_dir=tmp_path)
    baseline_payment = next(
        item.simulated_hour
        for item in baseline.event_trace
        if item.event_type == "customer_payment_received"
        and item.details.get("object_number") == "YAML-DRIVEN"
    )
    configured_payment = next(
        item.simulated_hour
        for item in configured.event_trace
        if item.event_type == "customer_payment_received"
        and item.details.get("object_number") == "YAML-DRIVEN"
    )

    assert configured_payment == baseline_payment - Decimal("144")
