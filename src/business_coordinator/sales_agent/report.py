"""Offline HTML report for the deterministic sales demo."""

from __future__ import annotations

from decimal import Decimal
from html import escape
from typing import Any


def _number(value: object) -> str:
    amount = Decimal(str(value))
    return f"{amount:,.2f}"


def _bar_group(title: str, values: list[tuple[str, object]], unit: str = "") -> str:
    maximum = max((abs(Decimal(str(value))) for _, value in values), default=Decimal("0"))
    rows = []
    for label, value in values:
        amount = Decimal(str(value))
        width = 0 if maximum == 0 else round(abs(amount) / maximum * 100)
        display = amount * 100 if unit == "%" else amount
        rows.append(
            f'<div class="bar-row"><span>{escape(label)}</span>'
            f'<div class="track"><div class="fill" style="width:{width}%"></div></div>'
            f"<strong>{escape(_number(display))}{escape(unit)}</strong></div>"
        )
    return f'<section class="panel"><h2>{escape(title)}</h2>{"".join(rows)}</section>'


def render_sales_report(result: dict[str, Any]) -> str:
    """Render a self-contained report that can be downloaded and opened locally."""
    warehouse = result["warehouse_comparison"]
    supplier = result["supplier_comparison"]
    metrics = warehouse["metrics"]
    supplier_metrics = supplier["metrics"]
    charts = "".join(
        _bar_group(
            title,
            [
                ("Baseline", metrics[key]["baseline"]),
                ("Warehouse +1", metrics[key]["alternative"]),
                ("Supplier expedite", supplier_metrics[key]["alternative"]),
            ],
            unit,
        )
        for key, title, unit in (
            ("ending_backlog", "Ending backlog", " orders"),
            ("average_waiting_hours", "Average waiting time", " h"),
            ("fulfilment_rate", "Fulfilment rate", "%"),
            ("stockout_count", "Stockouts", ""),
        )
    )
    finance_rows = "".join(
        "<tr>"
        f"<th>{escape(label)}</th>"
        f"<td>{escape(_number(metrics[key]['baseline']))}</td>"
        f"<td>{escape(_number(metrics[key]['alternative']))}</td>"
        f"<td>{escape(_number(supplier_metrics[key]['alternative']))}</td>"
        "</tr>"
        for key, label in (
            ("gross_profit", "Gross profit (SGD)"),
            ("accounts_receivable", "Accounts receivable (SGD)"),
            ("accounts_payable", "Accounts payable (SGD)"),
            ("ending_cash", "Ending cash (SGD)"),
            ("minimum_cash", "Minimum cash (SGD)"),
        )
    )
    exception_rows = "".join(
        f"<li>{escape(str(item['code']))}: "
        f"{escape(str(item.get('count', item.get('sku', ''))))}</li>"
        for item in result["exceptions"]
    )
    warning = escape(str(result.get("supplier_event_warning") or "None"))
    snapshot_id = escape(str(result["snapshot_id"]))
    baseline_id = escape(str(result["baseline_run_id"]))
    warehouse_id = escape(str(warehouse["alternative_run_id"]))
    supplier_id = escape(str(supplier["alternative_run_id"]))
    snapshot_hash = escape(str(warehouse["snapshot_hash"]))
    backlog = escape(str(result["actual_backlog"]))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sales Agent Demo Report</title>
<style>
body{{font:16px/1.5 system-ui,sans-serif;margin:0;background:#f4f7fb;color:#192537}}
main{{max-width:1100px;margin:auto;padding:32px 20px 56px}}
h1{{margin-bottom:4px}}h2{{font-size:1.1rem;margin:0 0 16px}}
.muted{{color:#5e6c7c}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(310px,1fr));gap:16px}}
.panel{{background:white;border:1px solid #dbe2ea;border-radius:12px;padding:20px;
margin:16px 0;box-shadow:0 2px 8px #1d2a3808}}
.kpi{{font-size:2.5rem;font-weight:700;color:#1457a3}}
.bar-row{{display:grid;grid-template-columns:122px 1fr 82px;gap:10px;
align-items:center;margin:12px 0;font-size:.9rem}}
.track{{height:16px;background:#e9eef5;border-radius:8px;overflow:hidden}}
.fill{{height:100%;background:#2980c3;border-radius:8px}}
.bar-row:nth-of-type(3) .fill{{background:#1e9479}}
.bar-row:nth-of-type(4) .fill{{background:#a875d1}}
table{{border-collapse:collapse;width:100%}}
th,td{{padding:10px 8px;border-bottom:1px solid #e2e8f0;text-align:right}}
th:first-child{{text-align:left}}
.warning{{border-left:4px solid #b7791f;background:#fff7e8;padding:12px 16px}}
code{{overflow-wrap:anywhere}}
</style></head><body><main>
<h1>Sales Agent Demo Report</h1>
<p class="muted">Actual Order-to-Cash state and isolated simulated scenarios</p>
<div class="panel"><h2>Actual state</h2><div class="kpi">{backlog}</div>
<div>Current backlog orders</div>
<p>Snapshot ID: <code>{snapshot_id}</code><br>Snapshot hash: <code>{snapshot_hash}</code></p>
<ul>{exception_rows}</ul></div>
<div class="grid">{charts}</div>
<section class="panel"><h2>Financial comparison (simulated)</h2>
<table><thead><tr><th>Metric</th><th>Baseline</th>
<th>Warehouse +1</th><th>Supplier expedite</th></tr></thead>
<tbody>{finance_rows}</tbody></table></section>
<section class="panel"><h2>Evidence and limits</h2>
<p>Baseline run: <code>{baseline_id}</code><br>
Warehouse run: <code>{warehouse_id}</code><br>
Supplier run: <code>{supplier_id}</code></p>
<p class="warning">Supplier event: {warning}</p>
<p>Scenario values are simulated, not actual outcomes. The demo's resource capacity
and opening balances include synthetic assumptions. Imported orders do not provide
full historical node transitions.</p>
</section></main></body></html>"""
