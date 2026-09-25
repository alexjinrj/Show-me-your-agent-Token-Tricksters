from __future__ import annotations

from fastapi.testclient import TestClient


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "additional_workers": 2,
        "horizon_days": 7,
        "random_seed": 42,
        "primary_metric": "average_waiting_hours",
        "guardrail_metrics": [
            "ending_backlog",
            "fulfilment_rate",
            "stockout_count",
        ],
    }
    payload.update(overrides)
    return payload


def test_sales_backlog_analysis_returns_matched_audited_result(
    client: TestClient,
) -> None:
    before = client.get("/api/snapshot").json()["manifest"]["content_hash"]

    response = client.post("/api/v1/sales/backlog-analysis", json=_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "sales-analysis-api-v1"
    assert body["status"] == "ok"
    assert body["tool_name"] == "analyze_sales_backlog_intervention"
    assert body["state_type"] == "simulated"
    result = body["data"]
    assert result["schema_version"] == "sales-analysis-result-v1"
    assert result["facts"]["state_type"] == "actual"
    assert result["cause_hypothesis"]["status"] == "candidate_not_proven"
    assert result["simulation_comparison"]["state_type"] == "simulated"
    assert result["simulation_comparison"]["horizon_days"] == 7
    assert result["simulation_comparison"]["random_seed"] == 42
    assert result["actual_state_unchanged"] is True
    assert (
        result["analysis_case"]["baseline_run_id"]
        != result["analysis_case"]["alternative_run_id"]
    )
    assert client.get("/api/snapshot").json()["manifest"]["content_hash"] == before


def test_sales_backlog_analysis_rejects_snapshot_override_and_invalid_inputs(
    client: TestClient,
) -> None:
    spoofed_snapshot = client.post(
        "/api/v1/sales/backlog-analysis",
        json={**_payload(), "snapshot_id": "00000000-0000-0000-0000-000000000000"},
    )
    invalid = client.post(
        "/api/v1/sales/backlog-analysis",
        json=_payload(additional_workers=0, horizon_days=0),
    )

    assert spoofed_snapshot.status_code == 422
    assert invalid.status_code == 422
