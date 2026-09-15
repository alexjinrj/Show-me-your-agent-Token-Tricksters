from __future__ import annotations

from fastapi import FastAPI, HTTPException

from business_coordinator.agent import (
    InventoryAgentResponse,
    build_inventory_agent_response,
)
from business_coordinator.inventory.recommendation import (
    StrategyRecommendation,
)
from business_coordinator.tools.inventory import (
    get_inventory_recommendation,
)

app = FastAPI(
    title="SME Business State Coordinator",
    version="0.1.0",
    description=("Deterministic inventory and simulation recommendation API"),
)


@app.get(
    "/api/v1/inventory/recommendation",
    response_model=StrategyRecommendation,
    tags=["inventory"],
)
def read_inventory_recommendation() -> StrategyRecommendation:
    try:
        return get_inventory_recommendation()
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=500,
            detail="Inventory recommendation is invalid",
        ) from exc


@app.get(
    "/api/v1/agent/inventory-recommendation",
    response_model=InventoryAgentResponse,
    tags=["agent"],
)
def read_inventory_agent_recommendation() -> InventoryAgentResponse:
    try:
        return build_inventory_agent_response()
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=500,
            detail="Inventory recommendation is invalid",
        ) from exc
