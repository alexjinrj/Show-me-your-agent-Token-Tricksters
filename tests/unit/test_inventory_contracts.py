from decimal import Decimal

import pytest
from pydantic import ValidationError

from tools.inventory.contracts import (
    INVENTORY_TOOL_INPUTS,
    ReorderCandidatesInput,
    StrategyAnalysisInput,
)

SNAPSHOT_ID = "00000000-0000-0000-0000-000000000001"


def test_inventory_tool_names_are_registered() -> None:
    assert set(INVENTORY_TOOL_INPUTS) == {
        "list_inventory_reorder_candidates",
        "compare_inventory_replenishment_strategies",
    }


def test_reorder_candidates_input_defaults() -> None:
    request = ReorderCandidatesInput(
        snapshot_id=SNAPSHOT_ID,
    )

    assert request.snapshot_id == SNAPSHOT_ID
    assert request.risk_level == "all"
    assert request.top_n == 10


def test_strategy_analysis_input_defaults() -> None:
    request = StrategyAnalysisInput(
        snapshot_id=SNAPSHOT_ID,
    )

    assert request.snapshot_id == SNAPSHOT_ID
    assert request.horizon_days == 30
    assert request.random_seed == 42
    assert request.effective_day == Decimal("3")


def test_reorder_candidates_rejects_invalid_top_n() -> None:
    with pytest.raises(ValidationError):
        ReorderCandidatesInput(
            snapshot_id=SNAPSHOT_ID,
            top_n=0,
        )


def test_inventory_input_rejects_invalid_snapshot_id() -> None:
    with pytest.raises(ValidationError):
        StrategyAnalysisInput(
            snapshot_id="not-a-valid-uuid",
        )


def test_inventory_input_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        StrategyAnalysisInput.model_validate(
            {
                "snapshot_id": SNAPSHOT_ID,
                "unknown_field": "not allowed",
            }
        )
