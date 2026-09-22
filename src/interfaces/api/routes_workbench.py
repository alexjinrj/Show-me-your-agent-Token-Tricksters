from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from tools.workbench.service import Document, SavePlan, Search, UpdatePlan, Workbench

router = APIRouter(prefix="/api/workbench", tags=["evidence and action tracking"])


def service(request: Request) -> Workbench:
    context = request.app.state.context
    return Workbench(context.engine, context.base_snapshot_id)


@router.post("/documents")
def add_document(body: Document, request: Request) -> dict[str, Any]:
    return service(request).add("document", body.model_dump(mode="json"))


@router.get("/documents")
def documents(request: Request, offset: int = Query(default=0, ge=0, le=10000)) -> dict[str, Any]:
    return service(request).search(Search(offset=offset))


@router.get("/plans")
def plans(request: Request) -> list[dict[str, Any]]:
    return service(request).list("plan")


@router.post("/plans")
def save_plan(body: SavePlan, request: Request) -> dict[str, Any]:
    try:
        return service(request).save_plan(body)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/plans/{plan_id}/status")
def update_plan(plan_id: str, body: UpdatePlan, request: Request) -> dict[str, Any]:
    try:
        return service(request).update(plan_id, body)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
