from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from core.models import ScenarioEvent, SimulationSession
from core.simulation.scenarios import (
    expedited_supplier_delivery,
    warehouse_capacity_increase,
)
from interfaces.api.app import get_context
from interfaces.api.context import DemoContext
from interfaces.api.schemas import (
    EventRequest,
    ForkRequest,
    PresetRequest,
    SessionCreateRequest,
)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])
ContextDependency = Annotated[DemoContext, Depends(get_context)]


def _serialize(session: SimulationSession) -> dict[str, Any]:
    return session.model_dump(mode="python")


@router.post("", status_code=201)
def create_session(
    request: SessionCreateRequest,
    context: ContextDependency,
) -> dict[str, Any]:
    snapshot_id = request.base_snapshot_id or context.base_snapshot_id
    try:
        session = context.simulations.create_session(snapshot_id, request.name, request.description)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _serialize(session)


@router.get("/{session_id}")
def get_session(
    session_id: str,
    context: ContextDependency,
) -> dict[str, Any]:
    try:
        session = context.simulations.get_session(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _serialize(session)


@router.post("/{session_id}/events")
def add_event(
    session_id: str,
    event: EventRequest,
    context: ContextDependency,
) -> dict[str, Any]:
    try:
        scenario_event = event.to_scenario_event()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        session = context.simulations.add_event(session_id, scenario_event)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _serialize(session)


@router.post("/{session_id}/events/preset")
def add_preset_event(
    session_id: str,
    request: PresetRequest,
    context: ContextDependency,
) -> dict[str, Any]:
    scenario_event: ScenarioEvent
    if request.preset == "warehouse_capacity_increase":
        scenario_event = warehouse_capacity_increase(workers=request.workers)
    else:
        scenario_event = expedited_supplier_delivery(
            request.purchase_order_number, days=request.days
        )
    try:
        session = context.simulations.add_event(session_id, scenario_event)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _serialize(session)


@router.post("/{session_id}/fork", status_code=201)
def fork_session(
    session_id: str,
    request: ForkRequest,
    context: ContextDependency,
) -> dict[str, Any]:
    try:
        child = context.simulations.fork_session(session_id, request.name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _serialize(child)
