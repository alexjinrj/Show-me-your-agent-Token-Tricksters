from __future__ import annotations

from fastapi.testclient import TestClient


def test_reorder_candidates_use_current_actual_snapshot(client: TestClient) -> None:
    manifest = client.get("/api/snapshot").json()["manifest"]

    response = client.get(
        "/api/v1/modules/inventory/reorder-candidates",
        params={"risk_level": "critical", "top_n": 2},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["tool_name"] == "list_inventory_reorder_candidates"
    assert body["state_type"] == "actual"
    assert body["reference_id"] == manifest["snapshot_id"]
    assert body["data"]["snapshot_hash"] == manifest["content_hash"]
    assert len(body["data"]["candidates"]) <= 2
    assert all(row["risk_level"] == "critical" for row in body["data"]["candidates"])


def test_strategy_comparison_returns_four_auditable_runs_without_mutation(
    client: TestClient,
) -> None:
    before = client.get("/api/snapshot").json()["manifest"]["content_hash"]

    response = client.post(
        "/api/v1/modules/inventory/strategy-comparison",
        json={"horizon_days": 7, "random_seed": 42, "effective_day": "2"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["tool_name"] == "compare_inventory_replenishment_strategies"
    assert body["state_type"] == "simulated"
    data = body["data"]
    assert [row["strategy"] for row in data["strategy_runs"]] == [
        "baseline",
        "critical_only",
        "demand_aligned",
        "full",
    ]
    assert all(row["simulation_run_id"] for row in data["strategy_runs"])
    assert all(row["result_hash"] for row in data["strategy_runs"])
    assert data["recommendation"]["actual_state_unchanged"] is True
    assert body["reference_id"] == data["recommendation"]["recommended_run_id"]
    assert client.get("/api/snapshot").json()["manifest"]["content_hash"] == before


def test_inventory_module_analysis_validates_browser_inputs(client: TestClient) -> None:
    candidates = client.get(
        "/api/v1/modules/inventory/reorder-candidates",
        params={"risk_level": "unknown", "top_n": 0},
    )
    strategy = client.post(
        "/api/v1/modules/inventory/strategy-comparison",
        json={"horizon_days": 0, "random_seed": 42, "effective_day": "-1"},
    )

    assert candidates.status_code == 422
    assert strategy.status_code == 422
