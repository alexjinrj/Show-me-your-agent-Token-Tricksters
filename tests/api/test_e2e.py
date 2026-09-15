from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import Session

from core.models import SnapshotBundle
from interfaces.api.context import DemoContext
from interfaces.api.settings import Settings


def test_full_demo_flow(client: TestClient) -> None:
    # Seed happened at startup: snapshot + processes available.
    assert client.get("/api/snapshot").status_code == 200
    assert client.get("/api/processes").status_code == 200

    # Create baseline + alternative sessions.
    baseline_id = client.post("/api/sessions", json={"name": "Baseline"}).json()[
        "simulation_session_id"
    ]
    alt_id = client.post("/api/sessions", json={"name": "Warehouse +1"}).json()[
        "simulation_session_id"
    ]

    # Add all three event types to the alternative.
    assert (
        client.post(
            f"/api/sessions/{alt_id}/events",
            json={"event_type": "order_arrival", "sku": "WB-H098", "quantity": "3"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/sessions/{alt_id}/events",
            json={
                "event_type": "resource_capacity_changed",
                "resource_type": "warehouse_staff",
                "capacity_delta": 1,
            },
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/sessions/{alt_id}/events",
            json={"event_type": "supplier_delivery_delayed", "days_delta": "-2"},
        ).status_code
        == 200
    )

    # Fork the alternative and confirm carry-over.
    fork = client.post(f"/api/sessions/{alt_id}/fork", json={"name": "Fork"})
    assert fork.status_code == 201
    assert len(fork.json()["scenario_events"]) == 3

    # Run and compare (deterministic).
    run = client.post(
        f"/api/sessions/{baseline_id}/run", json={"horizon_days": 30, "random_seed": 42}
    )
    assert run.status_code == 200
    assert len(run.json()["event_trace"]) > 0

    compare = client.post(
        "/api/compare",
        json={
            "baseline": {"session_id": baseline_id, "horizon_days": 30, "random_seed": 42},
            "alternative": {"session_id": alt_id, "horizon_days": 30, "random_seed": 42},
        },
    )
    assert compare.status_code == 200
    assert "comparison" in compare.json()

    # Assistant stub responds without mutating state.
    before = client.get("/api/snapshot").json()["manifest"]["content_hash"]
    assistant = client.post("/api/assistant", json={"message": "summarise"})
    assert assistant.status_code == 200
    assert assistant.json()["enabled"] is False
    after = client.get("/api/snapshot").json()["manifest"]["content_hash"]
    assert before == after


def test_simulation_receives_immutable_detached_snapshot(settings: Settings) -> None:
    context = DemoContext.bootstrap(settings)
    bundle = context.base_snapshot()
    # The simulation is handed a SnapshotBundle, never a writable ORM Session.
    assert isinstance(bundle, SnapshotBundle)
    assert not isinstance(bundle, Session)
    # Frozen pydantic model: cannot be mutated in place.
    with pytest.raises(ValidationError):
        bundle.manifest.content_hash = "tampered"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        bundle.records[0].data = {}  # type: ignore[misc]
