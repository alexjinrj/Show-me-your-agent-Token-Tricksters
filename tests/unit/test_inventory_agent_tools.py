from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

import tools.inventory.tools as inventory_tools_module
from core.models import (
    ScenarioEvent,
    SimulationRunResult,
    SnapshotBundle,
    SnapshotManifest,
    SnapshotRecord,
)
from enterprise_state.database import (
    create_schema,
    make_engine,
)
from tools.inventory.tools import InventoryAgentTools

SNAPSHOT_ID = "00000000-0000-0000-0000-000000000001"
NOW = datetime(2026, 9, 12, tzinfo=UTC)


class FakeActualState:
    def __init__(self, snapshot: SnapshotBundle) -> None:
        self.snapshot = snapshot

    def load_snapshot(
        self,
        snapshot_id: str,
    ) -> SnapshotBundle:
        assert snapshot_id == SNAPSHOT_ID
        return self.snapshot


class FakeStrategyResult:
    def model_dump(
        self,
        *,
        mode: str,
    ) -> dict[str, Any]:
        assert mode == "json"

        return {
            "recommendation": {
                "recommended_strategy": "demand_aligned",
                "replenishment_quantity": "43",
                "recommended_run_id": (
                    "00000000-0000-0000-0000-000000000099"
                ),
            },
            "demand_shortages": {
                "SKU-CRITICAL": "43",
            },
            "reorder_recommendations": [],
            "strategy_runs": [],
        }


def build_snapshot() -> SnapshotBundle:
    return SnapshotBundle(
        manifest=SnapshotManifest(
            snapshot_id=SNAPSHOT_ID,
            company_id="SG-SME-001",
            as_of_time=NOW,
            created_at=NOW,
            source_event_watermark=None,
            process_definition_versions={
                "order_to_cash": 2,
                "procure_to_pay": 2,
            },
            content_hash="a" * 64,
        ),
        records=(
            SnapshotRecord(
                record_type="item",
                record_key="SKU-CRITICAL",
                data={
                    "id": "item-critical",
                    "sku": "SKU-CRITICAL",
                    "name": "Critical Item",
                    "reorder_point": "3",
                },
            ),
            SnapshotRecord(
                record_type="item",
                record_key="SKU-HIGH",
                data={
                    "id": "item-high",
                    "sku": "SKU-HIGH",
                    "name": "High Risk Item",
                    "reorder_point": "3",
                },
            ),
            SnapshotRecord(
                record_type="inventory",
                record_key="inventory-critical",
                data={
                    "item_id": "item-critical",
                    "warehouse": "SG-WH-01",
                    "quantity": "0",
                },
            ),
            SnapshotRecord(
                record_type="inventory",
                record_key="inventory-high",
                data={
                    "item_id": "item-high",
                    "warehouse": "SG-WH-01",
                    "quantity": "1",
                },
            ),
        ),
    )


def build_agent_tools(
    snapshot: SnapshotBundle,
) -> InventoryAgentTools:
    tools = object.__new__(
        InventoryAgentTools
    )

    tools.engine = make_engine()
    create_schema(tools.engine)

    tools.actual = FakeActualState(
        snapshot
    )

    return tools


def test_lists_and_prioritizes_reorder_candidates() -> None:
    tools = build_agent_tools(build_snapshot())

    response = tools.call(
        "list_inventory_reorder_candidates",
        {
            "snapshot_id": SNAPSHOT_ID,
            "risk_level": "all",
            "top_n": 1,
        },
        agent_case_id="inventory-unit",
    )

    assert response.status == "ok"
    assert response.error_message is None

    result = response.data

    assert result["snapshot_id"] == SNAPSHOT_ID
    assert result["snapshot_hash"] == "a" * 64
    assert result["state_type"] == "actual"

    assert result["candidate_count"] == 2
    assert len(result["candidates"]) == 1

    first_candidate = result["candidates"][0]

    assert first_candidate["sku"] == "SKU-CRITICAL"
    assert first_candidate["risk_level"] == "critical"
    assert first_candidate["recommended_quantity"] == "6"


def test_compares_replenishment_strategies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = build_snapshot()
    tools = build_agent_tools(snapshot)

    observed: dict[str, Any] = {}

    def fake_strategy_analysis(
        received_snapshot: SnapshotBundle,
        *,
        horizon_days: int,
        random_seed: int,
        effective_day: Decimal,
        runner: Callable[[str, list[ScenarioEvent]], SimulationRunResult],
    ) -> FakeStrategyResult:
        assert callable(runner)
        observed.update(
            {
                "snapshot": received_snapshot,
                "horizon_days": horizon_days,
                "random_seed": random_seed,
                "effective_day": effective_day,
            }
        )

        return FakeStrategyResult()

    monkeypatch.setattr(
        inventory_tools_module,
        "run_inventory_strategy_analysis",
        fake_strategy_analysis,
    )

    response = tools.call(
        "compare_inventory_replenishment_strategies",
        {
            "snapshot_id": SNAPSHOT_ID,
            "horizon_days": 60,
            "random_seed": 99,
            "effective_day": "4",
        },
        agent_case_id="inventory-unit",
    )

    assert response.status == "ok"
    assert response.state_type == "simulated"
    assert response.reference_id == (
        "00000000-0000-0000-0000-000000000099"
    )

    result = response.data

    assert observed == {
        "snapshot": snapshot,
        "horizon_days": 60,
        "random_seed": 99,
        "effective_day": Decimal("4"),
    }

    assert result["state_type"] == "simulated"
    assert result["recommendation"]["recommended_strategy"] == ("demand_aligned")


def test_rejects_unknown_inventory_tool() -> None:
    tools = build_agent_tools(
        build_snapshot()
    )

    response = tools.call(
        "unknown_inventory_tool",
        {
            "snapshot_id": SNAPSHOT_ID,
        },
        agent_case_id="inventory-unit",
    )

    assert response.status == "error"
    assert (
        response.error_code
        == "NOT_AVAILABLE"
    )
    assert response.data == {}
