from __future__ import annotations

from dataclasses import replace

from fastapi.testclient import TestClient

from interfaces.api.app import create_app
from interfaces.api.settings import Settings

CUSTOMER_CSV = (
    "customer_number,name,active\n"
    "UPLOAD-C-1,Uploaded Customer,true\n"
)


def payload(csv_text: str = CUSTOMER_CSV) -> dict[str, object]:
    return {
        "filename": "customers.csv",
        "csv_text": csv_text,
        "source_type": "customers",
        "mapping_version": "browser-upload-v1",
        "data_origin": "source",
    }


def test_upload_inspection_is_read_only_and_commit_is_disabled_by_default(
    client: TestClient,
) -> None:
    before = client.get("/api/snapshot").json()["manifest"]["snapshot_id"]
    status = client.get("/api/v1/data/uploads/status").json()
    assert status["commit_enabled"] is False
    inspected = client.post("/api/v1/data/uploads/inspect", json=payload())
    assert inspected.status_code == 200
    body = inspected.json()
    assert body["inspection"]["probable_source_type"] == "customers"
    assert body["inspection"]["row_count"] == 1
    assert "path" not in body["inspection"]
    assert client.get("/api/snapshot").json()["manifest"]["snapshot_id"] == before
    assert client.post("/api/v1/data/uploads/commit", json=payload()).status_code == 503


def test_authorized_upload_refreshes_snapshot_runtime_and_is_idempotent(
    settings: Settings,
) -> None:
    app = create_app(replace(settings, upload_token="test-upload-token"))
    with TestClient(app) as client:
        before = client.get("/api/snapshot").json()
        unauthorized = client.post("/api/v1/data/uploads/commit", json=payload())
        assert unauthorized.status_code == 403

        response = client.post(
            "/api/v1/data/uploads/commit",
            json=payload(),
            headers={"X-Upload-Token": "test-upload-token"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["result"]["committed"] is True
        assert body["result"]["row_count"] == 1
        assert body["snapshot"]["snapshot_id"] != before["manifest"]["snapshot_id"]
        current = client.get("/api/snapshot").json()
        assert current["counts"]["customers"] == before["counts"]["customers"] + 1
        assert app.state.runtime.snapshot_id == current["manifest"]["snapshot_id"]

        duplicate = client.post(
            "/api/v1/data/uploads/commit",
            json=payload(),
            headers={"X-Upload-Token": "test-upload-token"},
        ).json()
        assert duplicate["result"]["committed"] is False
        assert duplicate["result"]["duplicate"] is True
        assert client.get("/api/snapshot").json()["counts"]["customers"] == (
            before["counts"]["customers"] + 1
        )


def test_invalid_upload_is_rejected_without_publishing_a_snapshot(settings: Settings) -> None:
    app = create_app(replace(settings, upload_token="test-upload-token"))
    invalid = "customer_number,name,active\nUPLOAD-C-2,Bad Customer,not-a-boolean\n"
    with TestClient(app) as client:
        before = client.get("/api/snapshot").json()["manifest"]["snapshot_id"]
        response = client.post(
            "/api/v1/data/uploads/commit",
            json=payload(invalid),
            headers={"X-Upload-Token": "test-upload-token"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["result"]["validation"]["valid"] is False
        assert body["snapshot"] is None
        assert client.get("/api/snapshot").json()["manifest"]["snapshot_id"] == before
