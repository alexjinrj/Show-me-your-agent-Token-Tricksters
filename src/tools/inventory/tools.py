from __future__ import annotations

import time
from decimal import Decimal
from typing import Any, Literal
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import Engine

from core.models import (
    ScenarioEvent,
    SimulationRunResult,
)
from core.serialization import canonical_data
from enterprise_state.service import (
    ActualStateService,
)
from tools.inventory.audit import (
    record_inventory_tool_call,
)
from tools.inventory.contracts import (
    INVENTORY_TOOL_INPUTS,
    InventoryToolInput,
    InventoryToolResponse,
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
from tools.simulation.service import (
    SimulationService,
)

RISK_ORDER = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
}


class InventoryAgentTools:
    """Bounded, audited Inventory Agent tools."""

    def __init__(
        self,
        engine: Engine,
    ) -> None:
        self.engine = engine
        self.actual = ActualStateService(
            engine
        )
        self.simulations = SimulationService(
            engine
        )

    @staticmethod
    def schemas() -> dict[
        str,
        dict[str, Any],
    ]:
        """Return schemas for Runtime registration."""

        return {
            name: input_model.model_json_schema()
            for name, input_model
            in INVENTORY_TOOL_INPUTS.items()
        }

    def call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        agent_case_id: str,
    ) -> InventoryToolResponse:
        """
        Validate, execute and audit one
        registered Inventory tool.
        """

        if (
            not agent_case_id
            or len(agent_case_id) > 80
        ):
            raise ValueError(
                "agent_case_id must contain "
                "1 to 80 characters"
            )

        started = time.perf_counter()
        call_id = str(uuid4())

        try:
            input_model = (
                INVENTORY_TOOL_INPUTS.get(
                    tool_name
                )
            )

            if input_model is None:
                raise ValueError(
                    "tool is not registered"
                )

            parsed = input_model.model_validate(
                arguments
            )

            (
                data,
                state_type,
                reference_id,
            ) = self._dispatch(parsed)

            response = InventoryToolResponse(
                tool_call_id=call_id,
                tool_name=tool_name,
                status="ok",
                state_type=state_type,
                reference_id=reference_id,
                data=canonical_data(data),
            )

        except (
            ValueError,
            ValidationError,
        ) as exc:
            response = InventoryToolResponse(
                tool_call_id=call_id,
                tool_name=tool_name,
                status="error",
                error_code=(
                    "INVALID_INPUT"
                    if isinstance(
                        exc,
                        ValidationError,
                    )
                    else "NOT_AVAILABLE"
                ),
                error_message=str(exc),
            )

        except Exception:
            response = InventoryToolResponse(
                tool_call_id=call_id,
                tool_name=tool_name,
                status="error",
                error_code="INTERNAL_ERROR",
                error_message=(
                    "Inventory tool execution "
                    "failed."
                ),
            )

        elapsed = max(
            0,
            round(
                (
                    time.perf_counter()
                    - started
                )
                * 1000
            ),
        )

        record_inventory_tool_call(
            self.engine,
            response,
            arguments,
            agent_case_id=agent_case_id,
            duration_ms=elapsed,
        )

        return response

    def _dispatch(
        self,
        request: InventoryToolInput,
    ) -> tuple[
        dict[str, Any],
        Literal["actual", "simulated"],
        str,
    ]:
        if isinstance(
            request,
            ReorderCandidatesInput,
        ):
            data = (
                self._list_reorder_candidates(
                    request
                )
            )

            return (
                data,
                "actual",
                request.snapshot_id,
            )

        if isinstance(
            request,
            StrategyAnalysisInput,
        ):
            data = (
                self._compare_replenishment_strategies(
                    request
                )
            )

            recommendation = data[
                "recommendation"
            ]

            reference_id = str(
                recommendation[
                    "recommended_run_id"
                ]
            )

            return (
                data,
                "simulated",
                reference_id,
            )

        raise ValueError(
            "unsupported inventory tool input: "
            f"{type(request).__name__}"
        )

    def _list_reorder_candidates(
        self,
        request: ReorderCandidatesInput,
    ) -> dict[str, Any]:
        snapshot = self.actual.load_snapshot(
            request.snapshot_id
        )

        rows = (
            extract_inventory_strategy_rows(
                snapshot
            )
        )

        recommendations = (
            build_reorder_recommendations(
                list(rows.item_rows),
                list(rows.inventory_rows),
            )
        )

        candidates = [
            row
            for row in recommendations
            if row.needs_reorder
            and (
                request.risk_level == "all"
                or row.risk_level
                == request.risk_level
            )
        ]

        candidates.sort(
            key=lambda row: (
                RISK_ORDER.get(
                    row.risk_level,
                    99,
                ),
                row.sku,
            )
        )

        total_recommended_quantity = sum(
            (
                candidate.recommended_quantity
                for candidate in candidates
            ),
            Decimal("0"),
        )

        return {
            "snapshot_id": (
                request.snapshot_id
            ),
            "snapshot_hash": (
                snapshot.manifest.content_hash
            ),
            "state_type": "actual",
            "candidate_count": len(
                candidates
            ),
            "total_recommended_quantity": (
                format(
                    total_recommended_quantity,
                    "f",
                )
            ),
            "candidates": [
                candidate.model_dump(
                    mode="json"
                )
                for candidate
                in candidates[
                    : request.top_n
                ]
            ],
        }

    def _compare_replenishment_strategies(
        self,
        request: StrategyAnalysisInput,
    ) -> dict[str, Any]:
        snapshot = self.actual.load_snapshot(
            request.snapshot_id
        )

        def persist(
            strategy: str,
            events: list[ScenarioEvent],
        ) -> SimulationRunResult:
            session = (
                self.simulations.create_session(
                    request.snapshot_id,
                    f"Inventory: {strategy}",
                )
            )

            for event in events:
                self.simulations.add_event(
                    session.simulation_session_id,
                    event,
                )

            return (
                self.simulations.run_session(
                    session.simulation_session_id,
                    snapshot,
                    horizon_days=(
                        request.horizon_days
                    ),
                    random_seed=(
                        request.random_seed
                    ),
                )
            )

        result = (
            run_inventory_strategy_analysis(
                snapshot,
                horizon_days=(
                    request.horizon_days
                ),
                random_seed=(
                    request.random_seed
                ),
                effective_day=(
                    request.effective_day
                ),
                runner=persist,
            )
        )

        return {
            "snapshot_id": (
                request.snapshot_id
            ),
            "snapshot_hash": (
                snapshot.manifest.content_hash
            ),
            "state_type": "simulated",
            **result.model_dump(
                mode="json"
            ),
        }