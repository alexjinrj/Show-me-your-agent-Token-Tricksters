#!/usr/bin/env python3
# ruff: noqa: E501
from __future__ import annotations

import argparse
import html
import webbrowser
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from business_coordinator.domain.models import ScenarioEvent, SimulationRunResult
from business_coordinator.persistence.database import create_schema, make_engine
from business_coordinator.persistence.service import ActualStateService, commit_demo_files
from business_coordinator.simulation import (
    SimulationService,
    expedited_supplier_delivery,
    warehouse_capacity_increase,
)
from business_coordinator.simulation.process_runtime import load_runtime_process_catalog

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
SNAPSHOT_TIME = datetime.fromisoformat("2026-09-12T23:59:00+08:00")


def _money(value: Decimal) -> str:
    return f"SGD {value:,.2f}"


def _number(value: Decimal) -> str:
    return f"{value:,.2f}"


def _metric_row(name: str, result: SimulationRunResult) -> str:
    metric = result.summary_metrics
    values = (
        name,
        str(metric.ending_backlog),
        f"{_number(metric.average_waiting_hours)} h",
        f"{_number(metric.fulfilment_rate * 100)}%",
        str(metric.stockout_count),
        _money(metric.gross_profit),
        _money(metric.ending_cash),
    )
    return "<tr>" + "".join(f"<td>{html.escape(value)}</td>" for value in values) + "</tr>"


def _timeline(events: list[tuple[str, str, str]]) -> str:
    return "".join(
        "<li><time>Hour "
        + html.escape(hour)
        + "</time><strong>"
        + html.escape(event)
        + "</strong><span>"
        + html.escape(details)
        + "</span></li>"
        for hour, event, details in events
    )


def _render_html(
    *,
    counts: dict[str, int],
    snapshot_time: datetime,
    snapshot_rows: int,
    scenarios: tuple[tuple[str, SimulationRunResult], ...],
    unchanged: bool,
    reproducible: bool,
) -> str:
    baseline = scenarios[0][1]
    capacity = scenarios[1][1]
    expedited = scenarios[2][1]
    new_order = scenarios[3][1]
    waiting_delta = (
        capacity.summary_metrics.average_waiting_hours
        - baseline.summary_metrics.average_waiting_hours
    )
    sales_id = next(
        event.object_id
        for event in new_order.event_trace
        if event.event_type == "order_entered_simulation" and event.simulated_hour == Decimal("24")
    )
    sales_events = [
        (str(event.simulated_hour), event.event_type, str(event.details))
        for event in new_order.event_trace
        if event.object_id == sales_id
    ]
    purchase_ids = {
        event.object_id
        for event in baseline.event_trace
        if event.process_id == "procure_to_pay" and event.event_type == "goods_received"
    }
    purchase_id = sorted(purchase_ids)[0]
    purchase_events = [
        (str(event.simulated_hour), event.event_type, str(event.details))
        for event in baseline.event_trace
        if event.object_id == purchase_id
    ]
    catalog = load_runtime_process_catalog()
    process_html = "".join(
        "<section><h3>"
        + html.escape(definition.label)
        + "</h3><div class='flow'>"
        + "<span class='arrow'>→</span>".join(
            f"<span>{html.escape(node.label)}</span>" for node in definition.nodes
        )
        + "</div></section>"
        for definition in catalog.definitions.values()
    )
    rows = "".join(_metric_row(name, result) for name, result in scenarios)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Token Tricksters Simulation Demo</title>
<style>
:root {{ color-scheme: light dark; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }}
body {{ max-width: 1180px; margin: 0 auto; padding: 32px 20px 64px; background: Canvas; color: CanvasText; }}
h1 {{ margin-bottom: 4px; }}
h2 {{ margin-top: 36px; }}
.subtle {{ opacity: .7; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; }}
.card {{ border: 1px solid color-mix(in srgb, CanvasText 18%, transparent); border-radius: 12px; padding: 16px; }}
.card strong {{ display: block; font-size: 1.5rem; margin-top: 6px; }}
.good {{ color: #16834a; }}
.warn {{ color: #b85c00; }}
.table-wrap {{ overflow-x: auto; }}
table {{ width: 100%; border-collapse: collapse; }}
th, td {{ text-align: right; padding: 11px 10px; border-bottom: 1px solid color-mix(in srgb, CanvasText 14%, transparent); white-space: nowrap; }}
th:first-child, td:first-child {{ text-align: left; }}
.flow {{ display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }}
.flow span:not(.arrow) {{ padding: 7px 10px; border-radius: 8px; background: color-mix(in srgb, #3977d4 16%, Canvas); }}
.arrow {{ opacity: .5; }}
.timelines {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 24px; }}
ol {{ list-style: none; padding: 0; }}
li {{ display: grid; grid-template-columns: 92px 1fr; gap: 4px 12px; padding: 10px 0; border-bottom: 1px solid color-mix(in srgb, CanvasText 12%, transparent); }}
li time {{ grid-row: 1 / span 2; opacity: .65; font-variant-numeric: tabular-nums; }}
li span {{ opacity: .72; overflow-wrap: anywhere; }}
code {{ overflow-wrap: anywhere; }}
@media (max-width: 620px) {{ body {{ padding-top: 20px; }} .arrow {{ display: none; }} }}
</style>
</head>
<body>
<h1>Token Tricksters: 30-day SME simulation</h1>
<p class="subtle">Actual-state snapshot at {html.escape(snapshot_time.isoformat())}; all scenarios use seed 42.</p>

<div class="grid">
  <div class="card">Snapshot records<strong>{snapshot_rows:,}</strong></div>
  <div class="card">Business objects<strong>{counts["business_objects"]:,}</strong></div>
  <div class="card">Warehouse +1 wait change<strong class="good">{_number(waiting_delta)} h</strong></div>
  <div class="card">Baseline ending cash<strong class="warn">{_money(baseline.summary_metrics.ending_cash)}</strong></div>
</div>

<h2>Scenario comparison</h2>
<div class="table-wrap"><table>
<thead><tr><th>Scenario</th><th>Backlog</th><th>Average wait</th><th>Fulfilment</th><th>Stockouts</th><th>Gross profit</th><th>Ending cash</th></tr></thead>
<tbody>{rows}</tbody>
</table></div>

<h2>Configured processes</h2>
{process_html}

<h2>Event journeys</h2>
<div class="timelines">
  <section><h3>New order on day 1</h3><ol>{_timeline(sales_events)}</ol></section>
  <section><h3>Purchase order</h3><ol>{_timeline(purchase_events)}</ol></section>
</div>

<h2>Safety and reproducibility</h2>
<div class="grid">
  <div class="card">Actual State unchanged<strong class="good">{unchanged}</strong></div>
  <div class="card">Repeated baseline hash matches<strong class="good">{reproducible}</strong></div>
  <div class="card">Supplier adjustment traced<strong>{any(event.event_type == "supplier_delivery_adjusted" for event in expedited.event_trace)}</strong></div>
</div>
<p class="subtle">Snapshot hash: <code>{html.escape(baseline.snapshot_hash)}</code></p>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Token Tricksters visual simulation demo")
    parser.add_argument("--data", type=Path, default=Path("data/demo/raw"))
    parser.add_argument("--output", type=Path, default=Path("demo-output/simulation-demo.html"))
    parser.add_argument(
        "--open", action="store_true", help="open the report in the default browser"
    )
    args = parser.parse_args()

    engine = make_engine()
    create_schema(engine)
    actual_state = ActualStateService(engine, source_system="microsoft-adventureworks-demo")
    commit_demo_files(
        actual_state,
        ((kind, args.data / f"{kind}.csv") for kind in INGESTION_ORDER),
    )
    actual_hash_before = actual_state.actual_state_hash()
    manifest = actual_state.create_snapshot(SNAPSHOT_TIME)
    snapshot = actual_state.load_snapshot(manifest.snapshot_id)

    service = SimulationService(engine)
    baseline_session = service.create_session(manifest.snapshot_id, "Baseline")
    capacity_session = service.fork_session(baseline_session.simulation_session_id, "Warehouse +1")
    service.add_event(capacity_session.simulation_session_id, warehouse_capacity_increase())
    expedited_session = service.fork_session(
        baseline_session.simulation_session_id, "Delivery -5 days"
    )
    service.add_event(expedited_session.simulation_session_id, expedited_supplier_delivery())
    order_session = service.fork_session(
        baseline_session.simulation_session_id, "New order on day 1"
    )
    service.add_event(
        order_session.simulation_session_id,
        ScenarioEvent(
            event_type="order_arrival",
            effective_day=Decimal("1"),
            payload={"sku": "TT-R982", "quantity": "2", "order_number": "DEMO-SO-0001"},
        ),
    )

    sessions = (
        ("Baseline", baseline_session.simulation_session_id),
        ("Warehouse +1", capacity_session.simulation_session_id),
        ("Delivery -5 days", expedited_session.simulation_session_id),
        ("New order on day 1", order_session.simulation_session_id),
    )
    scenarios = tuple(
        (
            name,
            service.run_session(
                session_id,
                snapshot,
                horizon_days=30,
                random_seed=42,
            ),
        )
        for name, session_id in sessions
    )
    repeated = service.run_session(
        baseline_session.simulation_session_id,
        snapshot,
        horizon_days=30,
        random_seed=42,
    )
    unchanged = actual_state.actual_state_hash() == actual_hash_before
    reproducible = scenarios[0][1].result_hash == repeated.result_hash
    report = _render_html(
        counts=actual_state.counts(),
        snapshot_time=manifest.as_of_time,
        snapshot_rows=len(snapshot.records),
        scenarios=scenarios,
        unchanged=unchanged,
        reproducible=reproducible,
    )
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    print(f"Visual demo: {output}")
    print(f"Actual State unchanged: {unchanged}")
    print(f"Baseline reproducible: {reproducible}")
    if args.open:
        webbrowser.open(output.as_uri())


if __name__ == "__main__":
    main()
