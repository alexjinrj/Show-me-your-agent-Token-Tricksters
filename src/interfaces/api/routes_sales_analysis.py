from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from interfaces.api.context import DemoContext
from tools.sales.contracts import AnalyzeBacklogInput, SalesMetricCode
from tools.sales.tools import SalesAgentTools

router = APIRouter(prefix="/api/v1/sales", tags=["sales-analysis"])


class SalesBacklogAnalysisRequest(BaseModel):
    """Browser controls for the bounded backlog analysis.

    The snapshot is always selected by the server, so callers cannot mix an
    arbitrary snapshot into the shared demo state.
    """

    model_config = ConfigDict(extra="forbid")

    additional_workers: int = Field(default=2, ge=1, le=20)
    horizon_days: int = Field(default=7, ge=1, le=365)
    random_seed: int = 42
    primary_metric: SalesMetricCode = "average_waiting_hours"
    guardrail_metrics: tuple[SalesMetricCode, ...] = (
        "ending_backlog",
        "fulfilment_rate",
        "stockout_count",
    )

    @model_validator(mode="after")
    def unique_evaluation_metrics(self) -> SalesBacklogAnalysisRequest:
        if self.primary_metric in self.guardrail_metrics:
            raise ValueError("primary_metric must not also be a guardrail")
        if len(set(self.guardrail_metrics)) != len(self.guardrail_metrics):
            raise ValueError("guardrail_metrics must be unique")
        if not self.guardrail_metrics:
            raise ValueError("at least one guardrail metric is required")
        return self


@router.post("/backlog-analysis")
def backlog_analysis(
    payload: SalesBacklogAnalysisRequest,
    request: Request,
) -> dict[str, Any]:
    """Run one audited, deterministic baseline-versus-intervention analysis."""

    context = request.app.state.context
    if not isinstance(context, DemoContext):  # pragma: no cover - defensive
        raise RuntimeError("demo context is not initialized")
    arguments = AnalyzeBacklogInput.model_validate(
        {
            "snapshot_id": context.base_snapshot_id,
            **payload.model_dump(mode="json"),
        }
    ).model_dump(mode="json")
    result = SalesAgentTools(context.engine).call(
        "analyze_sales_backlog_intervention",
        arguments,
        agent_case_id=f"web-sales-analysis:{uuid4()}",
    )
    return {
        "schema_version": "sales-analysis-api-v1",
        **result.model_dump(mode="json"),
    }
