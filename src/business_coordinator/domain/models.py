from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

StateType = Literal["actual", "simulated"]
DataOrigin = Literal["source", "derived", "synthetic"]


class CanonicalModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Lineage(CanonicalModel):
    source_system: str
    source_file_id: str
    source_record_id: str
    ingestion_run_id: str
    business_timestamp: datetime
    ingested_at: datetime
    mapping_version: str
    validation_status: Literal["valid"] = "valid"
    data_origin: DataOrigin


class Customer(Lineage):
    customer_id: str
    customer_number: str
    name: str
    active: bool


class Supplier(Lineage):
    supplier_id: str
    supplier_number: str
    name: str
    active: bool


class Item(Lineage):
    item_id: str
    sku: str
    name: str
    standard_cost: Decimal
    list_price: Decimal
    reorder_point: Decimal
    active: bool


class ResourceCapacity(Lineage):
    resource_id: str
    resource_type: str
    process_id: str
    node_id: str
    capacity_units: Decimal
    effective_at: datetime


class BusinessEvent(Lineage):
    event_id: str
    object_id: str
    object_type: Literal["sales_order", "purchase_order", "inventory", "balance"]
    event_type: str
    payload: dict[str, Any]
    state_type: Literal["actual"] = "actual"


class BusinessObject(Lineage):
    object_id: str
    object_number: str
    object_type: Literal["sales_order", "purchase_order"]
    process_id: Literal["order_to_cash", "procure_to_pay"]
    current_node_id: str
    status: str
    entered_node_at: datetime
    amount: Decimal
    quantity: Decimal
    priority: int = Field(ge=0)
    state_type: Literal["actual"] = "actual"


class SnapshotRecord(CanonicalModel):
    record_type: str
    record_key: str
    data: dict[str, Any]


class SnapshotManifest(CanonicalModel):
    snapshot_id: str
    company_id: str
    as_of_time: datetime
    created_at: datetime
    source_event_watermark: str | None
    process_definition_versions: dict[str, int]
    content_hash: str
    state_type: Literal["actual"] = "actual"


class SnapshotBundle(CanonicalModel):
    manifest: SnapshotManifest
    records: tuple[SnapshotRecord, ...]


ScenarioEventType = Literal[
    "order_arrival",
    "resource_capacity_changed",
    "supplier_delivery_delayed",
]


class ScenarioEvent(CanonicalModel):
    event_type: ScenarioEventType
    effective_day: Decimal = Field(default=Decimal("0"), ge=0)
    payload: dict[str, Any]

    @model_validator(mode="after")
    def validate_payload(self) -> ScenarioEvent:
        required = {
            "order_arrival": {"sku", "quantity"},
            "resource_capacity_changed": {"resource_type", "capacity_delta"},
            "supplier_delivery_delayed": {"days_delta"},
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
            try:
                delta_days = Decimal(str(self.payload["days_delta"]))
            except InvalidOperation as exc:
                raise ValueError("days_delta must be numeric") from exc
            if not delta_days.is_finite() or delta_days == 0:
                raise ValueError("days_delta must be a non-zero finite number")
        return self


class AccountingLine(CanonicalModel):
    account: str
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
    event_type: str
    object_id: str
    process_id: str
    details: dict[str, Any] = Field(default_factory=dict)


class SimulationMetrics(CanonicalModel):
    ending_backlog: int
    average_waiting_hours: Decimal
    fulfilment_rate: Decimal
    resource_utilization: dict[str, Decimal]
    stockout_count: int
    ending_inventory_quantity: Decimal
    ending_inventory_value: Decimal
    revenue: Decimal
    cost_of_goods_sold: Decimal
    gross_profit: Decimal
    accounts_receivable: Decimal
    accounts_payable: Decimal
    ending_cash: Decimal
    minimum_cash: Decimal


class SimulationRunResult(CanonicalModel):
    simulation_run_id: str
    status: Literal["completed"] = "completed"
    state_type: Literal["simulated"] = "simulated"
    snapshot_hash: str
    process_definition_version: str
    process_definition_hash: str
    scenario_event_hash: str
    horizon_days: int
    random_seed: int
    result_hash: str
    summary_metrics: SimulationMetrics
    event_trace: tuple[SimulationTraceEvent, ...]
    accounting_impacts: tuple[AccountingImpact, ...]


class SimulationSession(CanonicalModel):
    simulation_session_id: str
    base_snapshot_id: str
    name: str
    description: str = ""
    parent_session_id: str | None = None
    scenario_events: tuple[ScenarioEvent, ...] = ()
    state_type: Literal["simulated"] = "simulated"
