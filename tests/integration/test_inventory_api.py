from __future__ import annotations

import importlib
from decimal import Decimal
from types import ModuleType

import pytest
from fastapi.testclient import TestClient

from business_coordinator.inventory.recommendation import (
    StrategyRecommendation,
)


def api_module() -> ModuleType:
    return importlib.import_module("business_coordinator.api.app")


def example_recommendation() -> StrategyRecommendation:
    return StrategyRecommendation(
        recommended_strategy="demand_aligned",
        selection_method="pareto_dominance",
        baseline_run_id="baseline-run",
        recommended_run_id="recommended-run",
        replenishment_quantity=Decimal("43"),
        backlog_reduction=43,
        fulfilment_improvement=Decimal("0.43"),
        gross_profit_improvement=Decimal("125.71"),
        cash_improvement=Decimal("125.87"),
        actual_state_unchanged=True,
        assumptions=("Active orders represent demand.",),
        limitations=("Demo data only.",),
    )


def test_inventory_recommendation_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = api_module()
    expected = example_recommendation()

    monkeypatch.setattr(
        module,
        "get_inventory_recommendation",
        lambda: expected,
    )

    with TestClient(module.app) as client:
        response = client.get("/api/v1/inventory/recommendation")

    assert response.status_code == 200

    body = response.json()

    assert body["recommended_strategy"] == "demand_aligned"
    assert body["selection_method"] == "pareto_dominance"
    assert body["replenishment_quantity"] == "43"
    assert body["backlog_reduction"] == 43
    assert body["actual_state_unchanged"] is True


def test_missing_recommendation_returns_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = api_module()

    def raise_missing() -> StrategyRecommendation:
        raise FileNotFoundError("Recommendation does not exist")

    monkeypatch.setattr(
        module,
        "get_inventory_recommendation",
        raise_missing,
    )

    with TestClient(module.app) as client:
        response = client.get("/api/v1/inventory/recommendation")

    assert response.status_code == 404
    assert response.json()["detail"] == "Recommendation does not exist"
