from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator


def _validate_uuid_string(value: str) -> str:
    try:
        UUID(value)
    except ValueError as exc:
        raise ValueError("must be a valid UUID string") from exc
    return value


def _validate_aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("must include a timezone offset")
    return value


type UUIDString = Annotated[str, AfterValidator(_validate_uuid_string)]
type AwareDatetime = Annotated[datetime, AfterValidator(_validate_aware_datetime)]
type HashDigest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
StateType = Literal["actual", "simulated"]
DataOrigin = Literal["source", "derived", "synthetic"]
ProcessId = Literal["order_to_cash", "procure_to_pay"]
ObjectType = Literal["sales_order", "purchase_order", "inventory", "balance"]
ResourceType = Literal[
    "sales_staff",
    "finance_staff",
    "warehouse_staff",
    "inventory_planner",
    "procurement_staff",
    "supplier_capacity",
]
ScenarioEventType = Literal[
    "order_arrival",
    "resource_capacity_changed",
    "supplier_delivery_delayed",
]
type MetricValue = int | Decimal


class CanonicalModel(BaseModel):
    """Immutable base class for values crossing workstream boundaries."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Lineage(CanonicalModel):
    source_system: str = Field(min_length=1)
    source_file_id: UUIDString
    source_record_id: str = Field(min_length=1)
    ingestion_run_id: UUIDString
    business_timestamp: AwareDatetime
    ingested_at: AwareDatetime
    mapping_version: str = Field(min_length=1)
    validation_status: Literal["valid"] = "valid"
    data_origin: DataOrigin


class Customer(Lineage):
    customer_id: UUIDString
    customer_number: str = Field(min_length=1)
    name: str = Field(min_length=1)
    active: bool
    state_type: Literal["actual"] = "actual"


class Supplier(Lineage):
    supplier_id: UUIDString
    supplier_number: str = Field(min_length=1)
    name: str = Field(min_length=1)
    active: bool
    state_type: Literal["actual"] = "actual"


class Item(Lineage):
    item_id: UUIDString
    sku: str = Field(min_length=1)
    name: str = Field(min_length=1)
    standard_cost: Decimal = Field(ge=0)
    list_price: Decimal = Field(ge=0)
    reorder_point: Decimal = Field(ge=0)
    active: bool
    state_type: Literal["actual"] = "actual"


class ResourceCapacity(Lineage):
    resource_id: UUIDString
    resource_type: ResourceType
    process_id: ProcessId
    node_id: str = Field(min_length=1)
    capacity_units: Decimal = Field(ge=0)
    effective_at: AwareDatetime
    state_type: Literal["actual"] = "actual"


class BusinessEvent(Lineage):
    event_id: UUIDString
    object_id: UUIDString
    object_type: ObjectType
    event_type: str = Field(min_length=1)
    payload: dict[str, Any]
    state_type: Literal["actual"] = "actual"


class BusinessObject(Lineage):
    object_id: UUIDString
    object_number: str = Field(min_length=1)
    object_type: Literal["sales_order", "purchase_order"]
    process_id: ProcessId
    current_node_id: str = Field(min_length=1)
    status: str = Field(min_length=1)
    entered_node_at: AwareDatetime
    amount: Decimal = Field(ge=0)
    quantity: Decimal = Field(gt=0)
    priority: int = Field(default=0, ge=0)
    state_type: Literal["actual"] = "actual"

    @model_validator(mode="after")
    def process_matches_object_type(self) -> BusinessObject:
        expected = {
            "sales_order": "order_to_cash",
            "purchase_order": "procure_to_pay",
        }
        if self.process_id != expected[self.object_type]:
            raise ValueError("process_id does not match object_type")
        return self


class SnapshotRecord(CanonicalModel):
    record_type: str = Field(min_length=1)
    record_key: str = Field(min_length=1)
    data: dict[str, Any]


class SnapshotManifest(CanonicalModel):
    snapshot_id: UUIDString
    company_id: UUIDString
    as_of_time: AwareDatetime
    created_at: AwareDatetime
    source_event_watermark: str | None
    process_definition_versions: dict[ProcessId, int]
    content_hash: HashDigest
    state_type: Literal["actual"] = "actual"

    @field_validator("process_definition_versions")
    @classmethod
    def validate_process_versions(cls, value: dict[ProcessId, int]) -> dict[ProcessId, int]:
        required = {"order_to_cash", "procure_to_pay"}
        if set(value) != required:
            raise ValueError(f"must contain exactly these process IDs: {sorted(required)}")
        if any(version < 1 for version in value.values()):
            raise ValueError("process-definition versions must be positive integers")
        return value


class SnapshotBundle(CanonicalModel):
    manifest: SnapshotManifest
    records: tuple[SnapshotRecord, ...]
    state_type: Literal["actual"] = "actual"

    @field_validator("records")
    @classmethod
    def sort_and_validate_records(
        cls, records: tuple[SnapshotRecord, ...]
    ) -> tuple[SnapshotRecord, ...]:
        ordered = tuple(sorted(records, key=lambda record: (record.record_type, record.record_key)))
        keys = [(record.record_type, record.record_key) for record in ordered]
        if len(keys) != len(set(keys)):
            raise ValueError("snapshot record keys must be unique within each record type")
        return ordered


class ScenarioEvent(CanonicalModel):
    scenario_event_id: UUIDString
    event_type: ScenarioEventType
    effective_at: AwareDatetime
    payload: dict[str, Any]
    state_type: Literal["simulated"] = "simulated"


class SimulationTraceEvent(CanonicalModel):
    occurred_at: AwareDatetime
    event_type: str = Field(min_length=1)
    object_id: UUIDString | None = None
    node_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    state_type: Literal["simulated"] = "simulated"


class SimulationRunResult(CanonicalModel):
    simulation_run_id: UUIDString
    simulation_session_id: UUIDString
    snapshot_hash: HashDigest
    process_definition_versions: dict[ProcessId, int]
    process_definition_hash: HashDigest
    scenario_event_hash: HashDigest
    horizon_days: int = Field(gt=0)
    random_seed: int
    result_hash: HashDigest
    summary_metrics: dict[str, MetricValue]
    event_trace: tuple[SimulationTraceEvent, ...]
    state_type: Literal["simulated"] = "simulated"

    @field_validator("process_definition_versions")
    @classmethod
    def validate_process_versions(cls, value: dict[ProcessId, int]) -> dict[ProcessId, int]:
        if not value or any(version < 1 for version in value.values()):
            raise ValueError("process-definition versions must be non-empty and positive")
        return value
