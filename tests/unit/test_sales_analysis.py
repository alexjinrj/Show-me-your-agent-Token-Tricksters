from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from tools.sales.analysis import evaluate_sales_metrics
from tools.sales.contracts import AnalyzeBacklogInput


def metric(baseline: str, alternative: str) -> dict[str, Decimal]:
    first, second = Decimal(baseline), Decimal(alternative)
    return {"baseline": first, "alternative": second, "difference": second - first}


def test_analysis_input_rejects_duplicate_primary_and_guardrails() -> None:
    with pytest.raises(ValidationError):
        AnalyzeBacklogInput(
            snapshot_id="00000000-0000-0000-0000-000000000000",
            primary_metric="ending_backlog",
            guardrail_metrics=("ending_backlog",),
        )
    with pytest.raises(ValidationError):
        AnalyzeBacklogInput(
            snapshot_id="00000000-0000-0000-0000-000000000000",
            guardrail_metrics=("ending_backlog", "ending_backlog"),
        )


def test_metric_evaluation_applies_materiality_and_trade_off() -> None:
    assessments, verdict = evaluate_sales_metrics(
        {
            "average_waiting_hours": metric("10", "8"),
            "ending_backlog": metric("20", "21"),
            "fulfilment_rate": metric("0.5", "0.50001"),
        },
        ("average_waiting_hours", "ending_backlog", "fulfilment_rate"),
    )
    assert verdict == "trade_off"
    assert assessments["average_waiting_hours"].outcome == "improved"
    assert assessments["ending_backlog"].outcome == "worsened"
    assert assessments["fulfilment_rate"].outcome == "unchanged"


def test_metric_evaluation_reports_no_material_change() -> None:
    assessments, verdict = evaluate_sales_metrics(
        {
            "average_waiting_hours": metric("10", "10.009"),
            "ending_backlog": metric("20", "20"),
        },
        ("average_waiting_hours", "ending_backlog"),
    )
    assert verdict == "no_material_change"
    assert {row.outcome for row in assessments.values()} == {"unchanged"}
