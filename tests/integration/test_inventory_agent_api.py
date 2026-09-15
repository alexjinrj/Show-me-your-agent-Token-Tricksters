from __future__ import annotations

import importlib
from types import ModuleType

import pytest
from fastapi.testclient import TestClient

from business_coordinator.agent import (
    InventoryAgentResponse,
)


def api_module() -> ModuleType:
    return importlib.import_module("business_coordinator.api.app")


def example_response() -> InventoryAgentResponse:
    return InventoryAgentResponse(
        recommendation=("Use the demand aligned strategy and replenish 43 units."),
        operational_impact=(
            "Expected backlog reduction: 43; fulfilment improvement: 43.00 percentage points."
        ),
        financial_impact=(
            "Expected gross profit improvement: 125.71; expected cash improvement: 125.87."
        ),
        selection_method="pareto_dominance",
        baseline_run_id="baseline-run",
        recommended_run_id="recommended-run",
        actual_state_unchanged=True,
        assumptions=("Active orders represent demand.",),
        limitations=("Demo data only.",),
    )


def test_inventory_agent_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = api_module()
    expected = example_response()

    monkeypatch.setattr(
        module,
        "build_inventory_agent_response",
        lambda: expected,
    )

    with TestClient(module.app) as client:
        response = client.get("/api/v1/agent/inventory-recommendation")

    assert response.status_code == 200

    body = response.json()

    assert body["recommendation"] == ("Use the demand aligned strategy and replenish 43 units.")
    assert body["selection_method"] == "pareto_dominance"
    assert body["recommended_run_id"] == "recommended-run"
    assert body["actual_state_unchanged"] is True


def test_missing_agent_recommendation_returns_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = api_module()

    def raise_missing() -> InventoryAgentResponse:
        raise FileNotFoundError("Recommendation does not exist")

    monkeypatch.setattr(
        module,
        "build_inventory_agent_response",
        raise_missing,
    )

    with TestClient(module.app) as client:
        response = client.get("/api/v1/agent/inventory-recommendation")

    assert response.status_code == 404
    assert response.json()["detail"] == ("Recommendation does not exist")
