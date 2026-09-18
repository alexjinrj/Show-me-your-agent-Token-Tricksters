from __future__ import annotations

from fastapi.testclient import TestClient


def test_assistant_disabled_shape(client: TestClient) -> None:
    before = client.get("/api/snapshot").json()["manifest"]["content_hash"]
    response = client.post("/api/assistant", json={"message": "How is fulfilment?"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "disabled"
    assert body["enabled"] is False
    assert body["echo"] == "How is fulfilment?"
    assert "OpenClaw" in body["reply"]
    assert body["evidence"] == []
    assert client.get(f"/api/assistant/runs/{body['agent_run_id']}").json() == body
    # No state mutation: snapshot hash unchanged.
    after = client.get("/api/snapshot").json()["manifest"]["content_hash"]
    assert before == after


def test_assistant_carries_context_ids(client: TestClient) -> None:
    session_id = client.post("/api/sessions", json={"name": "Agent context"}).json()[
        "simulation_session_id"
    ]
    response = client.post(
        "/api/assistant",
        json={"message": "hi", "session_id": session_id},
    )
    body = response.json()
    assert response.status_code == 200
    assert body["session_id"] == session_id
    assert body["run_id"] is None


def test_assistant_rejects_empty_message(client: TestClient) -> None:
    assert client.post("/api/assistant", json={"message": ""}).status_code == 422
    assert client.post("/api/assistant", json={"message": "  "}).status_code == 422
    assert client.post("/api/assistant", json={"message": "hi", "run_id": "r1"}).status_code == 422
