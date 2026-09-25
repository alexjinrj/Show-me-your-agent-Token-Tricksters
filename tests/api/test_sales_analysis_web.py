from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from enterprise_state.models import SimulationRunRow, ToolCallAuditRow


def test_web_sales_analysis_is_matched_audited_and_read_only(client: TestClient) -> None:
    context = client.app.state.context
    before = context.actual_state.actual_state_hash()
    response = client.post(
        "/api/v1/sales/backlog-analysis",
        json={
            "snapshot_id": context.base_snapshot_id,
            "additional_workers": 2,
            "horizon_days": 7,
            "random_seed": 42,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    data = body["data"]
    case = data["analysis_case"]
    comparison = data["simulation_comparison"]
    assert body["schema_version"] == "sales-analysis-api-v1"
    assert data["facts"]["backlog_count"] == 100
    assert data["cause_hypothesis"]["status"] == "candidate_not_proven"
    assert comparison["verdict"] == "improved"
    assert comparison["baseline_run_id"] == case["baseline_run_id"]
    assert comparison["alternative_run_id"] == case["alternative_run_id"]
    assert comparison["baseline_run_id"] != comparison["alternative_run_id"]
    assert comparison["horizon_days"] == 7 and comparison["random_seed"] == 42
    assert data["actual_state_unchanged"] is True
    assert context.actual_state.actual_state_hash() == before
    with Session(context.engine) as db:
        assert db.get(SimulationRunRow, comparison["baseline_run_id"]) is not None
        assert db.get(SimulationRunRow, comparison["alternative_run_id"]) is not None
        assert db.get(ToolCallAuditRow, body["tool_call_id"]) is not None


def test_web_sales_analysis_rejects_invalid_or_foreign_scope(client: TestClient) -> None:
    context = client.app.state.context
    assert client.post(
        "/api/v1/sales/backlog-analysis",
        json={"snapshot_id": context.base_snapshot_id, "additional_workers": 0},
    ).status_code == 422
    assert client.post(
        "/api/v1/sales/backlog-analysis",
        json={"snapshot_id": "00000000-0000-0000-0000-000000000000"},
    ).status_code == 409
