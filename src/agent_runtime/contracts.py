from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class RuntimeToolResult(BaseModel):
    """Framework-neutral result envelope returned by every runtime tool."""

    model_config = ConfigDict(extra="forbid")

    tool_call_id: str
    tool_name: str
    status: Literal["ok", "error"]
    state_type: Literal["actual", "simulated"] | None = None
    reference_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
