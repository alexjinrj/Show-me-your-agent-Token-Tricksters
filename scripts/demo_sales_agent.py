#!/usr/bin/env python3
"""Run a repeatable sales-tool demonstration against a seeded Actual State DB."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from business_coordinator.persistence.database import make_engine, sqlite_url
from business_coordinator.persistence.models import StateSnapshotRow
from business_coordinator.sales_agent import SalesAgentTools
from business_coordinator.sales_agent.report import render_sales_report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="actual_state.db")
    parser.add_argument(
        "--report-dir",
        type=Path,
        help="Write demo.json and a self-contained index.html for offline visual review",
    )
    arguments = parser.parse_args()
    engine = make_engine(sqlite_url(arguments.database))
    with Session(engine) as database:
        snapshot = database.scalar(
            select(StateSnapshotRow).order_by(StateSnapshotRow.as_of_time.desc())
        )
        if snapshot is None:
            raise SystemExit("No snapshot found; run scripts/seed_demo_data.py first")
        snapshot_id = snapshot.id

    tools = SalesAgentTools(engine)

    def call(tool_name: str, **kwargs: object) -> dict[str, object]:
        response = tools.call(tool_name, kwargs, agent_case_id="sales-demo-001")
        if response.status != "ok":
            raise SystemExit(f"{tool_name}: {response.error_code}: {response.error_message}")
        return response.model_dump(mode="json")

    summary = call("get_actual_state_summary", snapshot_id=snapshot_id)
    exceptions = call("list_exceptions", snapshot_id=snapshot_id)
    bottleneck = call("trace_process_bottleneck", snapshot_id=snapshot_id)
    baseline_session = call("create_simulation_session", snapshot_id=snapshot_id, name="Baseline")
    parent_id = baseline_session["data"]["simulation_session_id"]
    baseline = call(
        "run_simulation", simulation_session_id=parent_id, horizon_days=30, random_seed=42
    )

    staffing = call("fork_simulation_session", simulation_session_id=parent_id, name="Warehouse +1")
    staffing_id = staffing["data"]["simulation_session_id"]
    call(
        "add_simulation_event",
        simulation_session_id=staffing_id,
        event_type="warehouse_capacity_increase",
        workers=1,
    )
    staffing_run = call(
        "run_simulation", simulation_session_id=staffing_id, horizon_days=30, random_seed=42
    )

    supplier = call(
        "fork_simulation_session", simulation_session_id=parent_id, name="Supplier expedite"
    )
    supplier_id = supplier["data"]["simulation_session_id"]
    supplier_event = call(
        "add_simulation_event",
        simulation_session_id=supplier_id,
        event_type="expedite_supplier_delivery",
        days=5,
    )
    supplier_run = call(
        "run_simulation", simulation_session_id=supplier_id, horizon_days=30, random_seed=42
    )

    baseline_run_id = baseline["data"]["simulation_run_id"]
    output = {
        "snapshot_id": snapshot_id,
        "actual_backlog": summary["data"]["backlog_count"],
        "exceptions": exceptions["data"]["exceptions"],
        "bottleneck": bottleneck["data"],
        "baseline_run_id": baseline_run_id,
        "warehouse_comparison": call(
            "compare_simulation_runs",
            baseline_run_id=baseline_run_id,
            alternative_run_id=staffing_run["data"]["simulation_run_id"],
        )["data"],
        "supplier_event_warning": supplier_event["data"]["warning"],
        "supplier_comparison": call(
            "compare_simulation_runs",
            baseline_run_id=baseline_run_id,
            alternative_run_id=supplier_run["data"]["simulation_run_id"],
        )["data"],
    }
    serialized = json.dumps(output, ensure_ascii=False, indent=2)
    if arguments.report_dir is not None:
        arguments.report_dir.mkdir(parents=True, exist_ok=True)
        (arguments.report_dir / "demo.json").write_text(serialized, encoding="utf-8")
        (arguments.report_dir / "index.html").write_text(
            render_sales_report(output), encoding="utf-8"
        )
        print(f"Report: {arguments.report_dir / 'index.html'}")
        print(f"Data: {arguments.report_dir / 'demo.json'}")
    else:
        print(serialized)


if __name__ == "__main__":
    main()
