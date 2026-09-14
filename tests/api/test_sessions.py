from __future__ import annotations

from fastapi.testclient import TestClient


def _create_session(client: TestClient, name: str = "Baseline") -> str:
    response = client.post("/api/sessions", json={"name": name})
    assert response.status_code == 201, response.text
    return str(response.json()["simulation_session_id"])


def test_create_and_get_session(client: TestClient) -> None:
    session_id = _create_session(client)
    fetched = client.get(f"/api/sessions/{session_id}")
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["name"] == "Baseline"
    assert body["scenario_events"] == []


def test_add_order_arrival_event(client: TestClient) -> None:
    session_id = _create_session(client)
    response = client.post(
        f"/api/sessions/{session_id}/events",
        json={
            "event_type": "order_arrival",
            "sku": "SKU-1",
            "quantity": "5",
            "unit_price": "12.50",
            "priority": 1,
        },
    )
    assert response.status_code == 200, response.text
    events = response.json()["scenario_events"]
    assert len(events) == 1
    assert events[0]["event_type"] == "order_arrival"
    assert events[0]["payload"]["quantity"] == "5"


def test_add_resource_capacity_event(client: TestClient) -> None:
    session_id = _create_session(client)
    response = client.post(
        f"/api/sessions/{session_id}/events",
        json={
            "event_type": "resource_capacity_changed",
            "resource_type": "warehouse_staff",
            "capacity_delta": 2,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["scenario_events"][0]["payload"]["capacity_delta"] == 2


def test_add_supplier_delay_event(client: TestClient) -> None:
    session_id = _create_session(client)
    response = client.post(
        f"/api/sessions/{session_id}/events",
        json={
            "event_type": "supplier_delivery_delayed",
            "days_delta": "-3",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["scenario_events"][0]["payload"]["days_delta"] == "-3"


def test_invalid_event_returns_422(client: TestClient) -> None:
    session_id = _create_session(client)
    # quantity must be > 0
    response = client.post(
        f"/api/sessions/{session_id}/events",
        json={"event_type": "order_arrival", "sku": "SKU-1", "quantity": "0"},
    )
    assert response.status_code == 422
    # zero capacity_delta must be rejected
    response = client.post(
        f"/api/sessions/{session_id}/events",
        json={
            "event_type": "resource_capacity_changed",
            "resource_type": "warehouse_staff",
            "capacity_delta": 0,
        },
    )
    assert response.status_code == 422


def test_preset_events(client: TestClient) -> None:
    session_id = _create_session(client)
    response = client.post(
        f"/api/sessions/{session_id}/events/preset",
        json={"preset": "warehouse_capacity_increase", "workers": 1},
    )
    assert response.status_code == 200
    assert response.json()["scenario_events"][0]["event_type"] == "resource_capacity_changed"


def test_fork_carries_over_events(client: TestClient) -> None:
    parent_id = _create_session(client, "Parent")
    client.post(
        f"/api/sessions/{parent_id}/events",
        json={
            "event_type": "resource_capacity_changed",
            "resource_type": "warehouse_staff",
            "capacity_delta": 1,
        },
    )
    fork = client.post(f"/api/sessions/{parent_id}/fork", json={"name": "Child"})
    assert fork.status_code == 201, fork.text
    child = fork.json()
    assert child["parent_session_id"] == parent_id
    assert len(child["scenario_events"]) == 1
    persisted = client.get(f"/api/sessions/{child['simulation_session_id']}")
    assert persisted.status_code == 200
    assert persisted.json()["parent_session_id"] == parent_id
    assert persisted.json()["scenario_events"] == child["scenario_events"]

    added = client.post(
        f"/api/sessions/{child['simulation_session_id']}/events",
        json={
            "event_type": "resource_capacity_changed",
            "resource_type": "finance_staff",
            "capacity_delta": 1,
        },
    )
    assert added.status_code == 200
    assert len(added.json()["scenario_events"]) == 2
    assert len(client.get(f"/api/sessions/{parent_id}").json()["scenario_events"]) == 1


def test_get_unknown_session_404(client: TestClient) -> None:
    assert client.get("/api/sessions/does-not-exist").status_code == 404
