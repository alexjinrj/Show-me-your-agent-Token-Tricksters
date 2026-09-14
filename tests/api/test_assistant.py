from __future__ import annotations

from fastapi.testclient import TestClient


def test_assistant_stub_shape(client: TestClient) -> None:
    before = client.get("/api/snapshot").json()["manifest"]["content_hash"]
    response = client.post("/api/assistant", json={"message": "How is fulfilment?"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "stub"
    assert body["enabled"] is False
    assert body["echo"] == "How is fulfilment?"
    assert "analysis agent not yet enabled" in body["reply"]
    # No state mutation: snapshot hash unchanged.
    after = client.get("/api/snapshot").json()["manifest"]["content_hash"]
    assert before == after


def test_assistant_carries_context_ids(client: TestClient) -> None:
    response = client.post(
        "/api/assistant",
        json={"message": "hi", "session_id": "s1", "run_id": "r1"},
    )
    body = response.json()
    assert body["session_id"] == "s1"
    assert body["run_id"] == "r1"


def test_assistant_rejects_empty_message(client: TestClient) -> None:
    assert client.post("/api/assistant", json={"message": ""}).status_code == 422
