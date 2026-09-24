from __future__ import annotations

from typing import Any, Literal, cast
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from agent_runtime.evaluation import CaseCriteria, evaluate_case
from agent_runtime.human_review import HumanReviewService
from enterprise_state.models import AgentRunRow

router = APIRouter(prefix="/api/assistant", tags=["agent controls"])


class ReviewDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approved", "rejected"]
    reviewer: str = Field(min_length=1, max_length=120)
    note: str = Field(default="", max_length=2000)


def _run(request: Request, run_id: UUID) -> dict[str, Any]:
    run = request.app.state.runtime.store.load(str(run_id))
    if run is None:
        raise HTTPException(404, "Agent run not found")
    return cast(dict[str, Any], run)


@router.get("/runs/{run_id}/evaluation")
def run_evaluation(run_id: UUID, request: Request) -> dict[str, Any]:
    run = _run(request, run_id)
    return {
        "agent_run_id": str(run_id),
        "guardrails": run.get("guardrails"),
        "observability": run.get("observability"),
        "human_review": run.get("human_review"),
    }


@router.post("/runs/{run_id}/evaluate-case")
def evaluate_run_case(run_id: UUID, body: CaseCriteria, request: Request) -> dict[str, Any]:
    return evaluate_case(_run(request, run_id), body)


@router.get("/runs/{run_id}/review")
def get_review(run_id: UUID, request: Request) -> dict[str, Any]:
    review = _run(request, run_id).get("human_review")
    if review is None:
        raise HTTPException(404, "This run has no reviewable recommendation")
    return cast(dict[str, Any], review)


@router.post("/runs/{run_id}/review")
def decide_review(run_id: UUID, body: ReviewDecision, request: Request) -> dict[str, Any]:
    service = HumanReviewService(request.app.state.context.engine)
    try:
        return service.decide(str(run_id), body.decision, body.reviewer, body.note)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/evaluation/summary")
def evaluation_summary(request: Request) -> dict[str, Any]:
    with Session(request.app.state.context.engine) as db:
        rows = db.scalars(select(AgentRunRow)).all()
    completed = sum(row.payload.get("status") == "completed" for row in rows)
    failed = sum(row.payload.get("status") == "failed" for row in rows)
    blocked = sum(
        (row.payload.get("guardrails") or {}).get("status") == "blocked" for row in rows
    )
    pending = sum(
        (row.payload.get("human_review") or {}).get("status") == "pending" for row in rows
    )
    return {
        "schema_version": "agent-evaluation-summary-v1",
        "total_runs": len(rows),
        "completed_runs": completed,
        "failed_runs": failed,
        "guardrail_blocked_runs": blocked,
        "pending_human_reviews": pending,
    }
