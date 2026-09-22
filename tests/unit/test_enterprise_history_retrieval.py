from __future__ import annotations

from datetime import datetime

from core.models import EnterpriseState, StateRecord
from tools.retrieval.contracts import History
from tools.retrieval.history import query_enterprise_history


def _state(*, reversible: bool = True) -> EnterpriseState:
    object_id = "sales_order:SO-1"
    order = StateRecord(
        record_id=object_id,
        record_kind="object",
        record_type="sales_order",
        project_id="COMPANY-1",
        data={
            "object_number": "SO-1",
            "status": "shipped",
            "current_activity_id": "record_customer_invoice",
            "sku": "SKU-1",
            "amount": "25.00",
        },
        version=3,
        state_type="actual",
    )
    first = StateRecord(
        record_id="event:1",
        record_kind="event",
        record_type="order_approved",
        project_id="COMPANY-1",
        data={
            "occurred_at": datetime.fromisoformat("2026-09-01T10:00:00+08:00"),
            "activity_id": "approve_order",
            "source_record_id": "TX-1",
            "changes": {
                object_id: {
                    "status": {"before": "new", "after": "approved"},
                    "current_activity_id": {
                        "before": "approve_order",
                        "after": "allocate_inventory",
                    },
                }
            },
        },
        references=(object_id,),
        state_type="actual",
    )
    activity = StateRecord(
        record_id="activity:2",
        record_kind="activity_run",
        record_type="ship_goods",
        project_id="COMPANY-1",
        data={
            "process_id": "order_to_cash",
            "activity_id": "ship_goods",
            "subject_record_id": object_id,
            "status": "completed",
            "occurred_at": datetime.fromisoformat("2026-09-02T10:00:00+08:00"),
        },
        references=(object_id,),
        state_type="actual",
    )
    second_data = {
        "occurred_at": datetime.fromisoformat("2026-09-02T10:00:00+08:00"),
        "activity_id": "ship_goods",
        "source_record_id": "TX-2",
    }
    if reversible:
        second_data["changes"] = {
            object_id: {
                "status": {"before": "approved", "after": "shipped"},
                "current_activity_id": {
                    "before": "allocate_inventory",
                    "after": "record_customer_invoice",
                },
            }
        }
    second = StateRecord(
        record_id="event:2",
        record_kind="event",
        record_type="goods_shipped",
        project_id="COMPANY-1",
        data=second_data,
        references=(object_id,),
        state_type="actual",
    )
    return EnterpriseState(
        scope_id="COMPANY-1:actual",
        project_id="COMPANY-1",
        state_version=6,
        as_of_time=datetime.fromisoformat("2026-09-02T10:00:00+08:00"),
        records={
            record.record_id: record
            for record in (order, first, activity, second)
        },
        state_type="actual",
    )


def _request(as_of: str, *, limit: int = 20, offset: int = 0) -> History:
    return History(
        object_type="sales_order",
        object_id="SO-1",
        as_of=as_of,
        fields=["status", "current_activity_id", "amount"],
        limit=limit,
        offset=offset,
    )


def test_reconstructs_object_state_by_reversing_later_event_changes() -> None:
    result = query_enterprise_history(
        _state(),
        _request("2026-09-01T12:00:00+08:00"),
    )

    assert result["reconstruction_status"] == "reconstructed"
    assert result["completeness"] == "complete_for_recorded_reversible_events"
    assert result["object"]["data"] == {
        "status": "approved",
        "current_activity_id": "allocate_inventory",
        "amount": "25.00",
    }
    assert [item["record_id"] for item in result["timeline"]] == ["event:1"]
    assert result["current_object_projection"]["data"]["status"] == "shipped"


def test_refuses_historical_state_when_event_has_no_reversible_changes() -> None:
    result = query_enterprise_history(
        _state(reversible=False),
        _request("2026-09-01T12:00:00+08:00"),
    )

    assert result["reconstruction_status"] == "unavailable"
    assert result["completeness"] == "unavailable"
    assert result["object"] is None
    assert result["current_object_projection"]["data"]["status"] == "shipped"
    assert "no reversible change set" in result["warnings"][0]


def test_current_projection_and_timeline_are_bounded_and_paginated() -> None:
    result = query_enterprise_history(
        _state(),
        _request("2026-09-02T10:00:00+08:00", limit=1),
    )

    assert result["reconstruction_status"] == "current_projection"
    assert result["completeness"] == "current_projection_only"
    assert result["object"]["data"]["status"] == "shipped"
    assert result["returned"] == 1
    assert result["total_timeline_records"] == 3
    assert result["next_offset"] == 1
