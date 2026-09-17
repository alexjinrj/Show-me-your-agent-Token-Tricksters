from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from interfaces.api.context import DemoContext
from tools.dashboard import BusinessDashboardService

router = APIRouter(prefix="/api/v1/modules", tags=["business-modules"])


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


@router.get("/accounting")
def accounting(request: Request) -> dict[str, Any]:
    context = _context(request)
    return _envelope(context, "accounting", _service(context).accounting())


@router.get("/operations")
def operations(request: Request) -> dict[str, Any]:
    context = _context(request)
    return _envelope(context, "operations", _service(context).operations())
