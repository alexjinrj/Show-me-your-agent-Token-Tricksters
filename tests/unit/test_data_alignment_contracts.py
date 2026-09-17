from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path

import yaml

from core.models import EnterpriseState, StateRecord
from core.object_schema import load_object_schema_registry, validate_process_object_contract
from core.process_config import load_process_definitions
from core.simulation.process_runtime import load_runtime_process_catalog
from enterprise_state.history_replay import HistoryReplayExecutor
from load_data.mapping import (
    ActivityMappingSpec,
    BindingMapping,
    FieldMapping,
    MappingCompiler,
    ObjectMappingSpec,
    load_mapping_spec,
)
from load_data.mapping_assistant import NoOpMappingAssistant, SourceProfile

PROCESS_DIRECTORY = Path(__file__).parents[2] / "src" / "core" / "process_definitions"


def sales_order_state(*, process_hash: str) -> EnterpriseState:
    record = StateRecord(
        record_id="sales_order:SO-1",
        record_kind="object",
        record_type="sales_order",
        project_id="COMPANY-1",
        data={
            "id": "SO-1-ID",
            "object_number": "SO-1",
            "object_type": "sales_order",
            "process_id": "order_to_cash",
            "current_activity_id": "receive_order",
            "status": "new",
            "entered_node_at": datetime.fromisoformat("2026-09-01T09:00:00+08:00"),
            "amount": Decimal("25"),
            "quantity": Decimal("5"),
            "priority": 0,
            "sku": "SKU-1",
            "due_at": datetime.fromisoformat("2026-09-03T09:00:00+08:00"),
            "sales_channel": "web",
        },
        state_type="actual",
    )
    return EnterpriseState(
        scope_id="COMPANY-1",
        project_id="COMPANY-1",
        as_of_time=datetime.fromisoformat("2026-09-01T09:00:00+08:00"),
        process_definition_hash=process_hash,
        records={record.record_id: record},
        state_type="actual",
    )


def test_object_schema_can_be_a_superset_of_process_requirements() -> None:
    registry = load_object_schema_registry()
    processes = load_process_definitions(PROCESS_DIRECTORY)

    validate_process_object_contract(processes, registry)

    sales_order = registry.definition("sales_order")
    assert "quantity" in sales_order.attributes
    assert "priority" in sales_order.attributes
    assert set(sales_order.attributes) > {"quantity", "status", "sku"}


def test_mapping_compiler_builds_object_and_activity_invocation() -> None:
    registry = load_object_schema_registry()
    compiler = MappingCompiler(registry)
    customer, as_of = compiler.compile_object(
        {
            "customer_code": "C-1",
            "display_name": "Customer One",
            "is_active": "true",
            "snapshot_time": "2026-09-01T09:00:00+08:00",
        },
        ObjectMappingSpec(
            mapping_version="customer-v1",
            target_object_type="customer",
            identity=("customer_number",),
            attributes={
                "customer_number": FieldMapping(source="customer_code"),
                "name": FieldMapping(source="display_name"),
                "active": FieldMapping(source="is_active", transform="boolean"),
            },
            as_of=FieldMapping(source="snapshot_time", transform="datetime"),
        ),
        project_id="COMPANY-1",
    )
    assert customer.record_id == "customer:C-1"
    assert customer.data["active"] is True
    assert as_of.isoformat() == "2026-09-01T09:00:00+08:00"

    catalog = load_runtime_process_catalog()
    state = sales_order_state(process_hash=catalog.content_hash)
    invocation = compiler.compile_activity(
        {
            "transaction_id": "TX-1",
            "order_number": "SO-1",
            "occurred_at": "2026-09-01T10:00:00+08:00",
        },
        ActivityMappingSpec(
            mapping_version="sales-history-v1",
            process_id="order_to_cash",
            activity_id="receive_order",
            source_record_id="transaction_id",
            occurred_at=FieldMapping(source="occurred_at", transform="datetime"),
            bindings={
                "subject": BindingMapping(
                    object_type="sales_order",
                    lookup={"object_number": "order_number"},
                )
            },
        ),
        state=state,
    )
    assert invocation.bindings == {"subject": "sales_order:SO-1"}


def test_history_replay_uses_yaml_operations_and_edges() -> None:
    catalog = load_runtime_process_catalog()
    state = sales_order_state(process_hash=catalog.content_hash)
    compiler = MappingCompiler(load_object_schema_registry())
    invocation = compiler.compile_activity(
        {
            "transaction_id": "TX-1",
            "order_number": "SO-1",
            "occurred_at": "2026-09-01T10:00:00+08:00",
        },
        ActivityMappingSpec(
            mapping_version="sales-history-v1",
            process_id="order_to_cash",
            activity_id="receive_order",
            source_record_id="transaction_id",
            occurred_at=FieldMapping(source="occurred_at", transform="datetime"),
            bindings={
                "subject": BindingMapping(
                    object_type="sales_order",
                    lookup={"object_number": "order_number"},
                )
            },
        ),
        state=state,
    )

    result = HistoryReplayExecutor(process_catalog=catalog).replay(state, [invocation])

    order = result.state.record("sales_order:SO-1")
    assert order.data["status"] == "open"
    assert order.data["current_activity_id"] == "review_credit"
    assert result.state.events()[0].record_type == "order_received"
    assert result.state.activity_runs()[0].record_type == "receive_order"
    assert result.state.state_type == "actual"

    repeated = HistoryReplayExecutor(process_catalog=catalog).replay(result.state, [invocation])
    assert repeated.state == result.state


def test_declared_dummy_activity_applies_known_effect(tmp_path: Path) -> None:
    for source in PROCESS_DIRECTORY.glob("*.yaml"):
        raw = yaml.safe_load(source.read_text(encoding="utf-8"))
        if source.stem == "order_to_cash":
            receive = raw["activities"][0]
            receive["semantic_status"] = "dummy"
            receive["execution_inputs"] = {"observed_status": {"type": "string", "required": True}}
            receive["operations"] = [
                {
                    "operation": "set",
                    "target": "subject.status",
                    "value_from": "execution.observed_status",
                }
            ]
        (tmp_path / source.name).write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    catalog = load_runtime_process_catalog(tmp_path)
    state = sales_order_state(process_hash=catalog.content_hash)
    compiler = MappingCompiler(load_object_schema_registry())
    invocation = compiler.compile_activity(
        {
            "transaction_id": "UNKNOWN-1",
            "order_number": "SO-1",
            "occurred_at": "2026-09-01T10:00:00+08:00",
            "observed_status": "accepted_unknown_reason",
        },
        ActivityMappingSpec(
            mapping_version="unknown-transaction-v1",
            process_id="order_to_cash",
            activity_id="receive_order",
            semantic_status="dummy",
            source_record_id="transaction_id",
            occurred_at=FieldMapping(source="occurred_at", transform="datetime"),
            bindings={
                "subject": BindingMapping(
                    object_type="sales_order",
                    lookup={"object_number": "order_number"},
                )
            },
            execution_inputs={"observed_status": FieldMapping(source="observed_status")},
        ),
        state=state,
    )

    result = HistoryReplayExecutor(process_catalog=catalog).replay(state, [invocation])

    assert result.state.record("sales_order:SO-1").data["status"] == ("accepted_unknown_reason")
    event = result.state.events()[0]
    assert event.data["semantic_status"] == "dummy"
    assert event.data["source_record_id"] == "UNKNOWN-1"


def test_mapping_assistant_is_an_optional_proposal_only_port() -> None:
    proposal = NoOpMappingAssistant().propose_mapping(
        SourceProfile(source_name="input.csv", columns=("id",), row_count=1),
        load_object_schema_registry(),
        load_runtime_process_catalog(),
    )
    assert proposal.status == "manual_mapping_required"
    assert proposal.proposed_mapping is None


def test_mapping_spec_loads_from_yaml_without_python_changes(tmp_path: Path) -> None:
    path = tmp_path / "customer-v1.yaml"
    path.write_text(
        """
mapping_type: object_snapshot
mapping_version: customer-v1
target_object_type: customer
identity: [customer_number]
attributes:
  customer_number: {source: customer_code}
  name: {source: customer_name}
  active: {source: is_active, transform: boolean}
as_of: {source: snapshot_time, transform: datetime}
""".strip(),
        encoding="utf-8",
    )

    mapping = load_mapping_spec(path)

    assert isinstance(mapping, ObjectMappingSpec)
    assert mapping.target_object_type == "customer"
