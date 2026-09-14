from __future__ import annotations

from fastapi.testclient import TestClient


def _session(client: TestClient, name: str = "Baseline") -> str:
    return str(client.post("/api/sessions", json={"name": name}).json()["simulation_session_id"])


def test_run_is_deterministic(client: TestClient) -> None:
    session_id = _session(client)
    payload = {"horizon_days": 30, "random_seed": 42}
    first = client.post(f"/api/sessions/{session_id}/run", json=payload)
    second = client.post(f"/api/sessions/{session_id}/run", json=payload)
    assert first.status_code == 200, first.text
    assert second.status_code == 200
    body = first.json()
    assert body["result_hash"] == second.json()["result_hash"]
    assert len(body["event_trace"]) > 0
    assert "summary_metrics" in body
    assert "accounting_impacts" in body
    assert body["actual_state_unchanged"] is True
    assert any(event["node_id"] for event in body["event_trace"])
    # Decimal serialized as string.
    assert isinstance(body["summary_metrics"]["revenue"], str)


def test_run_unknown_session_404(client: TestClient) -> None:
    response = client.post("/api/sessions/nope/run", json={"horizon_days": 30, "random_seed": 42})
    assert response.status_code == 404


def test_run_unknown_sku_returns_validation_error(client: TestClient) -> None:
    session_id = _session(client)
    event = client.post(
        f"/api/sessions/{session_id}/events",
        json={"event_type": "order_arrival", "sku": "NOT-A-SKU", "quantity": "1"},
    )
    assert event.status_code == 200
    response = client.post(
        f"/api/sessions/{session_id}/run", json={"horizon_days": 30, "random_seed": 42}
    )
    assert response.status_code == 422
    assert "unknown scenario SKU" in response.json()["detail"]


def test_compare_extra_warehouse_worker(client: TestClient) -> None:
    baseline_id = _session(client, "Baseline")
    alt_id = _session(client, "Warehouse +1")
    client.post(
        f"/api/sessions/{alt_id}/events/preset",
        json={"preset": "warehouse_capacity_increase", "workers": 1},
    )
    spec = {
        "baseline": {"session_id": baseline_id, "horizon_days": 30, "random_seed": 42},
        "alternative": {"session_id": alt_id, "horizon_days": 30, "random_seed": 42},
    }
    first = client.post("/api/compare", json=spec)
    second = client.post("/api/compare", json=spec)
    assert first.status_code == 200, first.text
    body = first.json()
    assert set(body) == {"baseline", "alternative", "comparison"}
    assert "average_waiting_hours" in body["comparison"]
    assert "ending_inventory_quantity" in body["comparison"]
    assert "minimum_cash" in body["comparison"]
    assert any(key.startswith("resource_utilization.") for key in body["comparison"])
    # Deterministic across repeated calls.
    assert body == second.json()
    # An extra warehouse worker reduces average waiting hours.
    diff = body["comparison"]["average_waiting_hours"]["difference"]
    assert diff.startswith("-") or diff == "0"
