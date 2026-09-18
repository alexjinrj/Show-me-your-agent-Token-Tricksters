from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent_runtime.service import RuntimeService

router = APIRouter(prefix="/api", tags=["assistant"])


class AssistantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=8000)
    conversation_id: UUID | None = None
    session_id: UUID | None = None
    run_id: UUID | None = None

    @field_validator("message")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message must not be blank")
        return value


@router.post("/assistant")
def assistant(body: AssistantRequest, request: Request) -> dict[str, Any]:
    runtime: RuntimeService = request.app.state.runtime
    try:
        return runtime.run(
            body.message,
            str(body.conversation_id) if body.conversation_id else None,
            str(body.session_id) if body.session_id else None,
            str(body.run_id) if body.run_id else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/assistant/runs/{agent_run_id}")
def get_agent_run(agent_run_id: UUID, request: Request) -> dict[str, Any]:
    runtime: RuntimeService = request.app.state.runtime
    run = runtime.store.load(str(agent_run_id))
    if run is None:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return run


@router.get("/assistant/status")
def assistant_status(request: Request) -> dict[str, Any]:
    runtime: RuntimeService = request.app.state.runtime
    return {
        "enabled": runtime.gateway is not None,
        "provider": "openclaw",
        "snapshot_id": runtime.snapshot_id,
        "tools": runtime.executor.registry.catalog(),
        "limits": {"max_rounds": runtime.max_rounds, "max_tool_calls": runtime.max_tool_calls},
    }
