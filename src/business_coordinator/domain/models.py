from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

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
