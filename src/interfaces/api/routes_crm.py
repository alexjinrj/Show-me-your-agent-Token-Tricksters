from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from interfaces.api.context import DemoContext

router = APIRouter(prefix="/api/v1/crm", tags=["crm"])
legacy_router = APIRouter(prefix="/api/crm", tags=["crm-compat"])


class CRMRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ProposalCreate(CRMRequest):
    complaint_id: str = Field(alias="complaintId", pattern=r"^CASE-SO\d{1,12}$")
    resolution_id: Literal["refund", "reship", "credit", "monitor"] = Field(alias="resolutionId")
    reply_draft: str = Field(default="", alias="replyDraft", max_length=4000)
    internal_draft: str = Field(default="", alias="internalDraft", max_length=4000)
    source_agent_run_id: UUID | None = Field(default=None, alias="sourceAgentRunId")
    source_tool_call_id: UUID | None = Field(default=None, alias="sourceToolCallId")

    @model_validator(mode="after")
    def paired_evidence(self) -> ProposalCreate:
        if (self.source_agent_run_id is None) != (self.source_tool_call_id is None):
            raise ValueError("Agent run and tool evidence references must be supplied together")
        return self


class ProposalDecision(CRMRequest):
    decision: Literal["Approved", "Rejected"]
    reviewer: str = Field(min_length=1, max_length=120)
    note: str = Field(default="", max_length=1000)

    @field_validator("reviewer")
    @classmethod
    def nonblank_reviewer(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Reviewer must not be blank")
        return value.strip()


def _context(request: Request) -> DemoContext:
    context = request.app.state.context
    if not isinstance(context, DemoContext):  # pragma: no cover - defensive
        raise RuntimeError("demo context is not initialized")
    return context


def _envelope(context: DemoContext, data: Any) -> dict[str, Any]:
    return {
        "schema_version": "crm-api-v1",
        "dataset_reference": context.crm.reference_id,
        "data": data,
        "provenance": context.crm.provenance(),
    }


def _not_found(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


@router.get("/provenance")
def provenance(request: Request) -> dict[str, Any]:
    context = _context(request)
    return _envelope(context, context.crm.provenance())


@router.get("/summary")
def summary(request: Request) -> dict[str, Any]:
    context = _context(request)
    return _envelope(context, context.crm.summary())


@router.get("/customers")
def customers(request: Request) -> dict[str, Any]:
    context = _context(request)
    return _envelope(context, context.crm.rate_customers())


@router.get("/customers/{customer_id}")
def customer(customer_id: str, request: Request) -> dict[str, Any]:
    context = _context(request)
    try:
        return _envelope(context, context.crm.customer(customer_id))
    except ValueError as exc:
        raise _not_found(exc) from exc


@router.get("/complaints")
def complaints(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=100)] = 24,
) -> dict[str, Any]:
    context = _context(request)
    return _envelope(context, context.crm.prioritize_complaints()[:limit])


@router.get("/complaints/{complaint_id}")
def complaint(complaint_id: str, request: Request) -> dict[str, Any]:
    context = _context(request)
    try:
        value = {
            **context.crm.complaint(complaint_id),
            "investigation": context.crm.investigate(complaint_id),
        }
        return _envelope(context, value)
    except ValueError as exc:
        raise _not_found(exc) from exc


@router.get("/proposals")
def proposals(request: Request, status: str | None = None) -> dict[str, Any]:
    context = _context(request)
    return _envelope(context, context.crm_proposals.list(status))


@router.post("/proposals", status_code=201)
def create_proposal(body: ProposalCreate, request: Request) -> dict[str, Any]:
    context = _context(request)
    try:
        result = context.crm_proposals.create(
            body.complaint_id,
            body.resolution_id,
            body.reply_draft,
            body.internal_draft,
            str(body.source_agent_run_id) if body.source_agent_run_id else None,
            str(body.source_tool_call_id) if body.source_tool_call_id else None,
        )
        return _envelope(context, result)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/proposals/{proposal_id}")
def proposal(proposal_id: UUID, request: Request) -> dict[str, Any]:
    context = _context(request)
    try:
        return _envelope(context, context.crm_proposals.get(str(proposal_id)))
    except ValueError as exc:
        raise _not_found(exc) from exc


@router.post("/proposals/{proposal_id}/decision")
def decide_proposal(proposal_id: UUID, body: ProposalDecision, request: Request) -> dict[str, Any]:
    context = _context(request)
    try:
        result = context.crm_proposals.decide(
            str(proposal_id), body.decision, body.reviewer, body.note
        )
        return _envelope(context, result)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


# Compatibility for the original green frontend while it migrates to the versioned contract.
@legacy_router.get("/summary", include_in_schema=False)
def legacy_summary(request: Request) -> dict[str, Any]:
    return _context(request).crm.summary()


@legacy_router.get("/customers", include_in_schema=False)
def legacy_customers(request: Request) -> list[dict[str, Any]]:
    return _context(request).crm.rate_customers()


@legacy_router.get("/customers/{customer_id}", include_in_schema=False)
def legacy_customer(customer_id: str, request: Request) -> dict[str, Any]:
    try:
        return _context(request).crm.customer(customer_id)
    except ValueError as exc:
        raise _not_found(exc) from exc


@legacy_router.get("/complaints", include_in_schema=False)
def legacy_complaints(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=100)] = 24,
) -> list[dict[str, Any]]:
    return _context(request).crm.prioritize_complaints()[:limit]


@legacy_router.get("/complaints/{complaint_id}", include_in_schema=False)
def legacy_complaint(complaint_id: str, request: Request) -> dict[str, Any]:
    try:
        return _context(request).crm.complaint(complaint_id)
    except ValueError as exc:
        raise _not_found(exc) from exc


@legacy_router.post("/proposals", include_in_schema=False, status_code=201)
def legacy_create_proposal(body: ProposalCreate, request: Request) -> dict[str, Any]:
    data = create_proposal(body, request)["data"]
    if not isinstance(data, dict):  # pragma: no cover - construction invariant
        raise RuntimeError("CRM proposal response is invalid")
    return data
