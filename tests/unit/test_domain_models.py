from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from core import (
    BusinessObject,
    Customer,
    ScenarioEvent,
    SimulationRunResult,
    SnapshotBundle,
    SnapshotManifest,
    SnapshotRecord,
    canonical_data,
    canonical_hash,
    canonical_json,
)

UUIDS = {
    "customer": "d737346b-034a-4dc2-9698-0f5d181954d3",
    "file": "d9dfc0e2-fb1c-4ad3-919e-26081e082637",
    "ingestion": "c7285906-f212-4559-bb72-7b30741a7849",
    "object": "13f7b046-e3f8-4772-b3fd-d7f75b302ee5",
    "snapshot": "8ef46301-b2ec-43a5-976a-0b2e71f0aa55",
    "company": "bff80bb8-2859-4df6-bc9d-f7508a386e86",
    "scenario": "4f981b75-1f87-45e2-8d8d-864bcb2a4f12",
}
NOW = datetime(2026, 9, 13, 9, 30, tzinfo=UTC)
HASH = "a" * 64


def lineage() -> dict[str, object]:
    return {
        "source_system": "demo_erp",
        "source_file_id": UUIDS["file"],
        "source_record_id": "row-1",
        "ingestion_run_id": UUIDS["ingestion"],
        "business_timestamp": NOW,
        "ingested_at": NOW,
        "mapping_version": "customer-v1",
        "data_origin": "source",
    }


def test_actual_record_is_typed_immutable_and_json_compatible() -> None:
    customer = Customer(
        **lineage(),
        customer_id=UUIDS["customer"],
        customer_number="C-001",
        name="Merlion Retail",
        active=True,
    )

    assert customer.state_type == "actual"
    assert canonical_data(customer)["business_timestamp"] == "2026-09-13T09:30:00+00:00"
    with pytest.raises(ValidationError):
        customer.name = "Changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value"),
    [("customer_id", "not-a-uuid"), ("business_timestamp", datetime(2026, 9, 13))],
)
def test_actual_record_rejects_invalid_identity_or_naive_time(field: str, value: object) -> None:
    values = {
        **lineage(),
        "customer_id": UUIDS["customer"],
        "customer_number": "C-001",
        "name": "Merlion Retail",
        "active": True,
        field: value,
    }

    with pytest.raises(ValidationError):
        Customer.model_validate(values)


def test_business_object_enforces_process_and_positive_quantity() -> None:
    values = {
        **lineage(),
        "object_id": UUIDS["object"],
        "object_number": "SO-001",
        "object_type": "sales_order",
        "process_id": "order_to_cash",
        "current_node_id": "order_received",
        "status": "open",
        "entered_node_at": NOW,
        "amount": Decimal("120.00"),
        "quantity": Decimal("2"),
    }
    assert BusinessObject.model_validate(values).state_type == "actual"

    with pytest.raises(ValidationError, match="does not match"):
        BusinessObject.model_validate({**values, "process_id": "procure_to_pay"})
    with pytest.raises(ValidationError):
        BusinessObject.model_validate({**values, "quantity": 0})


def test_snapshot_records_are_sorted_and_unique() -> None:
    manifest = SnapshotManifest(
        snapshot_id=UUIDS["snapshot"],
        company_id=UUIDS["company"],
        as_of_time=NOW,
        created_at=NOW,
        source_event_watermark=None,
        process_definition_versions={"procure_to_pay": 1, "order_to_cash": 1},
        content_hash=HASH,
    )
    records = (
        SnapshotRecord(record_type="item", record_key="B", data={"quantity": Decimal("2.0")}),
        SnapshotRecord(record_type="customer", record_key="A", data={"active": True}),
    )

    bundle = SnapshotBundle(manifest=manifest, records=records)
    assert [(record.record_type, record.record_key) for record in bundle.records] == [
        ("customer", "A"),
        ("item", "B"),
    ]
    assert canonical_json(bundle) == canonical_json(
        SnapshotBundle(manifest=manifest, records=tuple(reversed(records)))
    )

    with pytest.raises(ValidationError, match="must be unique"):
        SnapshotBundle(manifest=manifest, records=(records[0], records[0]))


def test_canonical_hash_ignores_mapping_order_and_preserves_decimal_semantics() -> None:
    first = {"amount": Decimal("10.00"), "nested": {"a": 1, "b": 2}}
    second = {"nested": {"b": 2, "a": 1}, "amount": Decimal("10.00")}

    assert canonical_json(first) == '{"amount":"10.00","nested":{"a":1,"b":2}}'
    assert canonical_hash(first) == canonical_hash(second)


def test_scenario_event_is_simulated_and_rejects_unknown_event_type() -> None:
    event = ScenarioEvent(
        scenario_event_id=UUIDS["scenario"],
        event_type="supplier_delivery_delayed",
        effective_at=NOW,
        payload={"purchase_order_id": UUIDS["object"], "delay_days": -2},
    )
    assert event.state_type == "simulated"

    with pytest.raises(ValidationError):
        ScenarioEvent(
            scenario_event_id=UUIDS["scenario"],
            event_type="actual_state_changed",  # type: ignore[arg-type]
            effective_at=NOW,
            payload={},
        )


def test_simulation_result_carries_reproducibility_contract() -> None:
    result = SimulationRunResult(
        simulation_run_id="70c50662-6ac9-4e8d-b18d-32f6446c61f7",
        simulation_session_id="5c3bb657-250a-4971-8b26-57d530fc091b",
        snapshot_hash="1" * 64,
        process_definition_versions={"order_to_cash": 1, "procure_to_pay": 1},
        process_definition_hash="2" * 64,
        scenario_event_hash="3" * 64,
        horizon_days=30,
        random_seed=42,
        result_hash="4" * 64,
        summary_metrics={"ending_cash": Decimal("91000.00"), "ending_backlog": 12},
        event_trace=(),
    )

    assert result.state_type == "simulated"
    assert canonical_data(result)["summary_metrics"]["ending_cash"] == "91000.00"
