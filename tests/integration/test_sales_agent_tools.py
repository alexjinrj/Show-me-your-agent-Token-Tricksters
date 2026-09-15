from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from business_coordinator.persistence.models import ToolCallAuditRow
from business_coordinator.persistence.service import ActualStateService, commit_demo_files
from business_coordinator.sales_agent import SalesAgentTools

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


def test_sales_tools_from_actual_state_through_scenarios(
    service: ActualStateService, demo_path: Path
) -> None:
    commit_demo_files(service, ((kind, demo_path / f"{kind}.csv") for kind in ORDER))
    actual_hash = service.actual_state_hash()
    snapshot = service.create_snapshot(datetime.fromisoformat("2026-09-12T23:59:00+08:00"))
    tools = SalesAgentTools(service.engine)

    def call(tool_name: str, **arguments: object) -> dict[str, object]:
        response = tools.call(tool_name, arguments, agent_case_id="sales-integration")
        assert response.status == "ok", response.error_message
        return response.data

    summary = call("get_actual_state_summary", snapshot_id=snapshot.snapshot_id)
    assert summary["sales_order_count"] == 500
    assert summary["backlog_count"] == 100
    assert summary["snapshot_hash"] == snapshot.content_hash
    exceptions = call("list_exceptions", snapshot_id=snapshot.snapshot_id)
    assert exceptions["exceptions"][0]["code"] == "ORDER_BACKLOG"
    bottleneck = call("trace_process_bottleneck", snapshot_id=snapshot.snapshot_id)
    assert bottleneck["current_backlog_by_node"]["allocate_inventory"] == 100
    assert bottleneck["actual_waiting_hours"] is None
    order_number = exceptions["exceptions"][0]["evidence_order_numbers"][0]
    trace = call(
        "trace_business_object", snapshot_id=snapshot.snapshot_id, order_number=order_number
    )
    assert trace["history_complete"] is False
    assert trace["total_events"] == 1
    history = call(
        "get_metric_history", snapshot_id=snapshot.snapshot_id, metric_code="average_waiting_hours"
    )
    assert history["availability"] == "not_available"

    baseline = call("create_simulation_session", snapshot_id=snapshot.snapshot_id, name="Baseline")
    baseline_session_id = baseline["simulation_session_id"]
    baseline_run = call(
        "run_simulation", simulation_session_id=baseline_session_id, horizon_days=30, random_seed=42
    )
    staffing = call(
        "fork_simulation_session", simulation_session_id=baseline_session_id, name="Warehouse +1"
    )
    staffing_id = staffing["simulation_session_id"]
    call(
        "add_simulation_event",
        simulation_session_id=staffing_id,
        event_type="warehouse_capacity_increase",
        workers=1,
    )
    alternative_run = call(
        "run_simulation", simulation_session_id=staffing_id, horizon_days=30, random_seed=42
    )
    comparison = call(
        "compare_simulation_runs",
        baseline_run_id=baseline_run["simulation_run_id"],
        alternative_run_id=alternative_run["simulation_run_id"],
    )
    assert Decimal(comparison["metrics"]["average_waiting_hours"]["difference"]) < 0
    supplier = call(
        "fork_simulation_session",
        simulation_session_id=baseline_session_id,
        name="Supplier expedite",
    )
    supplier_id = supplier["simulation_session_id"]
    supplier_event = call(
        "add_simulation_event",
        simulation_session_id=supplier_id,
        event_type="expedite_supplier_delivery",
        days=5,
    )
    assert "not among current backlog SKUs" in supplier_event["warning"]
    supplier_run = call(
        "run_simulation", simulation_session_id=supplier_id, horizon_days=30, random_seed=42
    )
    supplier_comparison = call(
        "compare_simulation_runs",
        baseline_run_id=baseline_run["simulation_run_id"],
        alternative_run_id=supplier_run["simulation_run_id"],
    )
    assert Decimal(supplier_comparison["metrics"]["ending_backlog"]["difference"]) == 0
    assert (
        call("get_simulation_state", simulation_session_id=baseline_session_id)["scenario_events"]
        == []
    )
    assert service.actual_state_hash() == actual_hash

    with Session(service.engine) as database:
        audit_count = database.scalar(select(func.count()).select_from(ToolCallAuditRow))
        assert audit_count == 16
        assert (
            database.scalar(
                select(func.count())
                .select_from(ToolCallAuditRow)
                .where(ToolCallAuditRow.status == "error")
            )
            == 0
        )


def test_tool_guards_and_audit(service: ActualStateService) -> None:
    tools = SalesAgentTools(service.engine)
    invalid = tools.call(
        "get_actual_state_summary", {"snapshot_id": "bad", "sql": "SELECT *"}, agent_case_id="guard"
    )
    assert invalid.status == "error"
    assert invalid.error_code == "INVALID_INPUT"
    unknown = tools.call("run_sql", {}, agent_case_id="guard")
    assert unknown.status == "error"
    with Session(service.engine) as database:
        assert database.scalar(select(func.count()).select_from(ToolCallAuditRow)) == 2
