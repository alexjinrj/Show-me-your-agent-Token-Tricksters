from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from interfaces.api.context import DemoContext
from tools.dashboard import BusinessDashboardService
from tools.inventory import InventoryAgentTools

router = APIRouter(prefix="/api/v1/modules", tags=["business-modules"])


class InventoryStrategyRequest(BaseModel):
    """Browser-safe controls for a detached inventory simulation."""

    model_config = ConfigDict(extra="forbid")

    horizon_days: int = Field(default=30, ge=1, le=365)
    random_seed: int = 42
    effective_day: Decimal = Field(default=Decimal("3"), ge=0)


def _context(request: Request) -> DemoContext:
    context = request.app.state.context
    if not isinstance(context, DemoContext):  # pragma: no cover - defensive
        raise RuntimeError("demo context is not initialized")
    return context


def _service(context: DemoContext) -> BusinessDashboardService:
    return BusinessDashboardService(context.base_snapshot())


def _envelope(context: DemoContext, module: str, data: dict[str, Any]) -> dict[str, Any]:
    manifest = context.base_manifest()
    return {
        "schema_version": "business-modules-v1",
        "module": module,
        "snapshot_reference": manifest.snapshot_id,
        "data": data,
        "provenance": {
            "state_type": manifest.state_type,
            "snapshot_hash": manifest.content_hash,
            "as_of": manifest.as_of_time,
            "source_system": "Microsoft AdventureWorks demo subset",
            "boundary": (
                "Source, derived and synthetic values preserve their data_origin labels. "
                "Module reads do not mutate Actual State."
            ),
        },
    }


@router.get("/overview")
def overview(request: Request) -> dict[str, Any]:
    context = _context(request)
    return _envelope(context, "overview", _service(context).overview(context.crm.summary()))


@router.get("/sales")
def sales(request: Request) -> dict[str, Any]:
    context = _context(request)
    return _envelope(context, "sales", _service(context).sales())


@router.get("/inventory")
def inventory(request: Request) -> dict[str, Any]:
    context = _context(request)
    return _envelope(context, "inventory", _service(context).inventory())


@router.get("/inventory/reorder-candidates")
def inventory_reorder_candidates(
    request: Request,
    risk_level: Literal["all", "critical", "high", "medium", "low"] = "all",
    top_n: int = Query(default=10, ge=1, le=100),
) -> dict[str, Any]:
    """Return audited reorder evidence from the current Actual State."""

    context = _context(request)
    result = InventoryAgentTools(context.engine).call(
        "list_inventory_reorder_candidates",
        {
            "snapshot_id": context.base_snapshot_id,
            "risk_level": risk_level,
            "top_n": top_n,
        },
        agent_case_id="inventory-dashboard",
    )
    return result.model_dump(mode="json")


@router.post("/inventory/strategy-comparison")
def inventory_strategy_comparison(
    payload: InventoryStrategyRequest,
    request: Request,
) -> dict[str, Any]:
    """Persist four isolated strategy runs without mutating Actual State."""

    context = _context(request)
    result = InventoryAgentTools(context.engine).call(
        "compare_inventory_replenishment_strategies",
        {
            "snapshot_id": context.base_snapshot_id,
            **payload.model_dump(mode="json"),
        },
        agent_case_id="inventory-dashboard",
    )
    return result.model_dump(mode="json")


@router.get("/accounting")
def accounting(request: Request) -> dict[str, Any]:
    context = _context(request)
    return _envelope(context, "accounting", _service(context).accounting())


@router.get("/operations")
def operations(request: Request) -> dict[str, Any]:
    context = _context(request)
    return _envelope(context, "operations", _service(context).operations())
