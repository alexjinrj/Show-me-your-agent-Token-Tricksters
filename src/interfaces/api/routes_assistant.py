from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(prefix="/api", tags=["assistant"])

DISABLED_NOTICE = "analysis agent not yet enabled"


class AssistantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1)
    session_id: str | None = None
    run_id: str | None = None


class AssistantResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["stub"] = "stub"
    reply: str
    echo: str
    session_id: str | None = None
    run_id: str | None = None
    enabled: Literal[False] = False


@router.post("/assistant", response_model=AssistantResponse)
def assistant(request: AssistantRequest) -> AssistantResponse:
    """Reserved endpoint for the future LangGraph analysis agent.

    This is a read-only stub: it never mutates Actual State, snapshots, sessions,
    or simulation runs. It simply echoes the incoming message together with a
    clearly-marked "not yet enabled" notice.

    TODO(analysis-agent): replace this stub with a LangGraph agent that reads the
    referenced snapshot/run (read-only) and produces grounded analysis. The agent
    must continue to treat all persisted state as immutable.
    """
    return AssistantResponse(
        reply=f"{DISABLED_NOTICE}. You said: {request.message}",
        echo=request.message,
        session_id=request.session_id,
        run_id=request.run_id,
    )
