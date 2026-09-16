from __future__ import annotations

from typing import Any

from sqlalchemy import Engine

from enterprise_state.service import ActualStateService
from tools.inventory.contracts import (
    INVENTORY_TOOL_INPUTS,
    ReorderCandidatesInput,
    StrategyAnalysisInput,
)
from tools.inventory.reorder import (
    build_reorder_recommendations,
)
from tools.inventory.snapshot_adapter import (
    extract_inventory_strategy_rows,
)
from tools.inventory.strategy import (
    run_inventory_strategy_analysis,
)

RISK_ORDER = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
}


class InventoryAgentTools:
    """Read-only Agent-callable inventory tools."""

    def __init__(self, engine: Engine) -> None:
        self.actual = ActualStateService(engine)

    @staticmethod
    def schemas() -> dict[str, dict[str, Any]]:
        """Return JSON schemas for Runtime registration."""

        return {
            name: input_model.model_json_schema()
            for name, input_model in INVENTORY_TOOL_INPUTS.items()
        }

    def call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Validate and execute one registered inventory tool."""

        input_model = INVENTORY_TOOL_INPUTS.get(tool_name)

        if input_model is None:
            raise ValueError(f"inventory tool is not registered: {tool_name}")

        parsed = input_model.model_validate(arguments)

        if isinstance(parsed, ReorderCandidatesInput):
            return self._list_reorder_candidates(parsed)

        if isinstance(parsed, StrategyAnalysisInput):
            return self._compare_replenishment_strategies(parsed)

        raise ValueError(f"unsupported inventory tool input: {type(parsed).__name__}")

    def _list_reorder_candidates(
        self,
        request: ReorderCandidatesInput,
    ) -> dict[str, Any]:
        snapshot = self.actual.load_snapshot(request.snapshot_id)
        rows = extract_inventory_strategy_rows(snapshot)

        recommendations = build_reorder_recommendations(
            list(rows.item_rows),
            list(rows.inventory_rows),
        )

        candidates = [
            row
            for row in recommendations
            if row["needs_reorder"] == "true"
            and (request.risk_level == "all" or row["risk_level"] == request.risk_level)
        ]

        candidates.sort(
            key=lambda row: (
                RISK_ORDER.get(row["risk_level"], 99),
                row["sku"],
            )
        )

        return {
            "snapshot_id": request.snapshot_id,
            "snapshot_hash": snapshot.manifest.content_hash,
            "state_type": "actual",
            "candidate_count": len(candidates),
            "candidates": candidates[: request.top_n],
        }

    def _compare_replenishment_strategies(
        self,
        request: StrategyAnalysisInput,
    ) -> dict[str, Any]:
        snapshot = self.actual.load_snapshot(request.snapshot_id)

        result = run_inventory_strategy_analysis(
            snapshot,
            horizon_days=request.horizon_days,
            random_seed=request.random_seed,
            effective_day=request.effective_day,
        )

        return {
            "snapshot_id": request.snapshot_id,
            "snapshot_hash": snapshot.manifest.content_hash,
            "state_type": "simulated",
            **result.model_dump(mode="json"),
        }
