from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request

from tools.sales.contracts import AnalyzeBacklogInput
from tools.sales.tools import SalesAgentTools

router = APIRouter(prefix="/api/v1/sales", tags=["sales analysis"])


@router.post("/backlog-analysis")
def analyze_backlog(body: AnalyzeBacklogInput, request: Request) -> dict[str, Any]:
    context = request.app.state.context
    if body.snapshot_id != context.base_snapshot_id:
        raise HTTPException(status_code=409, detail="Snapshot is outside request scope")
    result = SalesAgentTools(context.engine).call(
        "analyze_sales_backlog_intervention",
        body.model_dump(mode="json"),
        agent_case_id=f"web-sales-analysis:{uuid4()}",
    )
    if result.status != "ok":
        raise HTTPException(
            status_code=422 if result.error_code == "INVALID_INPUT" else 409,
            detail={"error_code": result.error_code, "message": result.error_message},
        )
    return {"schema_version": "sales-analysis-api-v1", **result.model_dump(mode="json")}
