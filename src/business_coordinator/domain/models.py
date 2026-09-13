from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
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
    "purchasing_staff",
    "supplier_capacity",
]
ScenarioEventType = Literal[
    "order_arrival",
    "resource_capacity_changed",
    "supplier_delivery_delayed",
]
type MetricValue = int | Decimal


def _default_process_versions() -> dict[ProcessId, int]:
    return {"order_to_cash": 1, "procure_to_pay": 1}


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
    company_id: str = Field(min_length=1)
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
    scenario_event_id: UUIDString | None = None
    event_type: ScenarioEventType
    effective_day: Decimal = Field(default=Decimal("0"), ge=0)
    effective_at: AwareDatetime | None = None
    payload: dict[str, Any]
    state_type: Literal["simulated"] = "simulated"

    @model_validator(mode="after")
    def validate_payload(self) -> ScenarioEvent:
        required = {
            "order_arrival": {"sku", "quantity"},
            "resource_capacity_changed": {"resource_type", "capacity_delta"},
            "supplier_delivery_delayed": set(),
        }[self.event_type]
        missing = sorted(required - self.payload.keys())
        if missing:
            raise ValueError(f"{self.event_type} payload is missing: {missing}")
        if self.event_type == "order_arrival":
            try:
                quantity = Decimal(str(self.payload["quantity"]))
                unit_price = Decimal(str(self.payload.get("unit_price", "1")))
            except InvalidOperation as exc:
                raise ValueError("order arrival quantity and unit price must be numeric") from exc
            if not quantity.is_finite() or quantity <= 0:
                raise ValueError("order arrival quantity must be greater than zero")
            if not unit_price.is_finite() or unit_price <= 0:
                raise ValueError("order arrival unit price must be greater than zero")
            priority = self.payload.get("priority", 0)
            if not isinstance(priority, int) or isinstance(priority, bool) or priority < 0:
                raise ValueError("order arrival priority must be a nonnegative integer")
        if self.event_type == "resource_capacity_changed":
            delta = self.payload["capacity_delta"]
            if not isinstance(delta, int) or isinstance(delta, bool) or delta == 0:
                raise ValueError("capacity_delta must be a non-zero integer")
        if self.event_type == "supplier_delivery_delayed":
            delay_key = "days_delta" if "days_delta" in self.payload else "delay_days"
            if delay_key not in self.payload:
                raise ValueError("supplier_delivery_delayed payload requires days_delta")
            try:
                delta_days = Decimal(str(self.payload[delay_key]))
            except InvalidOperation as exc:
                raise ValueError("days_delta must be numeric") from exc
            if not delta_days.is_finite() or delta_days == 0:
                raise ValueError("days_delta must be a non-zero finite number")
        return self


class AccountingLine(CanonicalModel):
    account: str = Field(min_length=1)
    debit: Decimal = Field(default=Decimal("0"), ge=0)
    credit: Decimal = Field(default=Decimal("0"), ge=0)


class AccountingImpact(CanonicalModel):
    event_type: str
    object_id: str
    simulated_hour: Decimal
    lines: tuple[AccountingLine, ...]


class SimulationTraceEvent(CanonicalModel):
    sequence: int
    simulated_hour: Decimal
    event_type: str = Field(min_length=1)
    object_id: str
    process_id: str
    occurred_at: AwareDatetime | None = None
    node_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    state_type: Literal["simulated"] = "simulated"


class SimulationMetrics(CanonicalModel):
    ending_backlog: int
    average_waiting_hours: Decimal = Decimal("0")
    fulfilment_rate: Decimal = Decimal("0")
    resource_utilization: dict[str, Decimal] = Field(default_factory=dict)
    stockout_count: int = 0
    ending_inventory_quantity: Decimal = Decimal("0")
    ending_inventory_value: Decimal = Decimal("0")
    revenue: Decimal = Decimal("0")
    cost_of_goods_sold: Decimal = Decimal("0")
    gross_profit: Decimal = Decimal("0")
    accounts_receivable: Decimal = Decimal("0")
    accounts_payable: Decimal = Decimal("0")
    ending_cash: Decimal = Decimal("0")
    minimum_cash: Decimal = Decimal("0")


class SimulationRunResult(CanonicalModel):
    simulation_run_id: UUIDString
    simulation_session_id: UUIDString | None = None
    status: Literal["completed"] = "completed"
    state_type: Literal["simulated"] = "simulated"
    snapshot_hash: HashDigest
    process_definition_version: str = ""
    process_definition_versions: dict[ProcessId, int] = Field(
        default_factory=_default_process_versions
    )
    process_definition_hash: HashDigest
    scenario_event_hash: HashDigest
    horizon_days: int = Field(gt=0)
    random_seed: int
    result_hash: HashDigest
    summary_metrics: SimulationMetrics
    event_trace: tuple[SimulationTraceEvent, ...]
    accounting_impacts: tuple[AccountingImpact, ...] = ()


class SimulationSession(CanonicalModel):
    simulation_session_id: UUIDString
    base_snapshot_id: UUIDString
    name: str = Field(min_length=1)
    description: str = ""
    parent_session_id: UUIDString | None = None
    scenario_events: tuple[ScenarioEvent, ...] = ()
    state_type: Literal["simulated"] = "simulated"
