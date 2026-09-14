from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

WEB_DIR = Path(__file__).parents[2] / "web"


def test_index_served_at_root(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Business Coordinator" in response.text


def test_app_js_served(client: TestClient) -> None:
    response = client.get("/app.js")
    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]


def test_styles_served(client: TestClient) -> None:
    response = client.get("/styles.css")
    assert response.status_code == 200


def test_spa_references_endpoints_and_controls() -> None:
    app_js = (WEB_DIR / "app.js").read_text(encoding="utf-8")
    # Task 8: scenario run + comparison endpoints referenced.
    assert "/run" in app_js
    assert "/api/compare" in app_js
    assert "/api/sessions" in app_js
    # Task 9: playback controls + utilization present.
    for control in ("play", "pause", "step", "scrub"):
        assert control in app_js
    assert "resource_utilization" in app_js
    assert "event.node_id" in app_js
    assert "actual_state_unchanged" in app_js
    assert "/fork" in app_js
    assert 'timeZone: "Asia/Singapore"' in app_js
    assert "toISOString" in app_js
    # Task 10: assistant panel posts to the stub endpoint.
    assert "/api/assistant" in app_js


def test_index_has_playback_and_chat_panels() -> None:
    index = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    for control_id in ('id="play"', 'id="pause"', 'id="step"', 'id="scrub"'):
        assert control_id in index
    assert 'id="chat-form"' in index
    assert 'id="comparison-table"' in index
