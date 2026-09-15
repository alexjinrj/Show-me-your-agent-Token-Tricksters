from __future__ import annotations

from interfaces.reports.sales_report import render_sales_report


def test_report_is_offline_and_escapes_tool_text() -> None:
    names = (
        "ending_backlog",
        "average_waiting_hours",
        "fulfilment_rate",
        "stockout_count",
        "gross_profit",
        "accounts_receivable",
        "accounts_payable",
        "ending_cash",
        "minimum_cash",
    )
    metrics = {name: {"baseline": "10", "alternative": "8", "difference": "-2"} for name in names}
    metrics["fulfilment_rate"] = {"baseline": "0.57", "alternative": "0.60", "difference": "0.03"}
    report = render_sales_report(
        {
            "snapshot_id": "snapshot-1",
            "actual_backlog": 100,
            "exceptions": [{"code": "ORDER_BACKLOG", "count": 100}],
            "baseline_run_id": "run-1",
            "supplier_event_warning": "<script>alert(1)</script>",
            "warehouse_comparison": {
                "alternative_run_id": "run-2",
                "snapshot_hash": "hash-1",
                "metrics": metrics,
            },
            "supplier_comparison": {"alternative_run_id": "run-3", "metrics": metrics},
        }
    )
    assert "57.00%" in report
    assert "run-1" in report and "run-2" in report and "run-3" in report
    assert "&lt;script&gt;" in report
    assert "<script>" not in report
    assert "https://" not in report
