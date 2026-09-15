from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from core.models import SimulationRunResult
from interfaces.api.app import get_context
from interfaces.api.context import DemoContext
from interfaces.api.schemas import CompareRequest, RunRequest, RunSpec

router = APIRouter(prefix="/api", tags=["simulation"])
ContextDependency = Annotated[DemoContext, Depends(get_context)]


def _run_spec(context: DemoContext, spec: RunSpec) -> SimulationRunResult:
    """Execute one run against a fresh, detached snapshot bundle.

    ``context.base_snapshot()`` returns an immutable ``SnapshotBundle`` (frozen
    pydantic models) with no ORM session attached, guaranteeing the simulation
    never receives a writable database handle.
    """
    snapshot = context.base_snapshot()
    return context.simulations.run_session(
        spec.session_id,
        snapshot,
        horizon_days=spec.horizon_days,
        random_seed=spec.random_seed,
    )


@router.post("/sessions/{session_id}/run")
def run_session(
    session_id: str,
    request: RunRequest,
    context: ContextDependency,
) -> dict[str, Any]:
    spec = RunSpec(
        session_id=session_id,
        horizon_days=request.horizon_days,
        random_seed=request.random_seed,
    )
    try:
        context.simulations.get_session(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    actual_hash_before = context.base_manifest().content_hash
    try:
        result = _run_spec(context, spec)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    actual_hash_after = context.base_manifest().content_hash
    payload = result.model_dump(mode="python")
    payload["actual_state_unchanged"] = actual_hash_before == actual_hash_after
    return payload


@router.post("/compare")
def compare(
    request: CompareRequest,
    context: ContextDependency,
) -> dict[str, Any]:
    try:
        context.simulations.get_session(request.baseline.session_id)
        context.simulations.get_session(request.alternative.session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        baseline = _run_spec(context, request.baseline)
        alternative = _run_spec(context, request.alternative)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    comparison = context.simulations.compare_runs(baseline, alternative)
    return {
        "baseline": {
            "simulation_run_id": baseline.simulation_run_id,
            "result_hash": baseline.result_hash,
            "summary_metrics": baseline.summary_metrics.model_dump(mode="python"),
        },
        "alternative": {
            "simulation_run_id": alternative.simulation_run_id,
            "result_hash": alternative.result_hash,
            "summary_metrics": alternative.summary_metrics.model_dump(mode="python"),
        },
        "comparison": comparison,
    }
