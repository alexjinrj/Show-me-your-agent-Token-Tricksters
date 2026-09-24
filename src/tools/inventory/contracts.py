from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from core.models import UUIDString


class InventoryToolInput(BaseModel):
    """Base input model for inventory Agent tools."""

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


INVENTORY_TOOL_INPUTS: dict[
    str,
    type[InventoryToolInput],
] = {
    "list_inventory_reorder_candidates": ReorderCandidatesInput,
    "compare_inventory_replenishment_strategies": StrategyAnalysisInput,
}
