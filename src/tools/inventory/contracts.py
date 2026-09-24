from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from core.models import UUIDString


class InventoryToolInput(BaseModel):
    """Base input model for Inventory Agent tools."""

    model_config = ConfigDict(extra="forbid")


class ReorderCandidatesInput(InventoryToolInput):
    """Input for listing inventory reorder candidates."""

    snapshot_id: UUIDString
    risk_level: Literal[
        "all",
        "critical",
        "high",
        "medium",
        "low",
    ] = "all"
    top_n: int = Field(default=10, ge=1, le=100)


class StrategyAnalysisInput(InventoryToolInput):
    """Input for comparing inventory replenishment strategies."""

    snapshot_id: UUIDString
    horizon_days: int = Field(default=30, ge=1, le=365)
    random_seed: int = 42
    effective_day: Decimal = Field(
        default=Decimal("3"),
        ge=0,
    )


class InventoryToolResponse(BaseModel):
    """Standard response returned by every Inventory Agent tool."""

    model_config = ConfigDict(extra="forbid")

    tool_call_id: UUIDString
    tool_name: str
    status: Literal["ok", "error"]
    state_type: Literal["actual", "simulated"] | None = None
    reference_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None


INVENTORY_TOOL_INPUTS: dict[
    str,
    type[InventoryToolInput],
] = {
    "list_inventory_reorder_candidates": ReorderCandidatesInput,
    "compare_inventory_replenishment_strategies": StrategyAnalysisInput,
}