from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SourceFileRow(Base):
    __tablename__ = "source_files"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_system: Mapped[str] = mapped_column(String(100))
    file_name: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    row_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class IngestionRunRow(Base):
    __tablename__ = "ingestion_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_file_id: Mapped[str] = mapped_column(ForeignKey("source_files.id"))
    source_type: Mapped[str] = mapped_column(String(50))
    mapping_version: Mapped[str] = mapped_column(String(50))
    validation_status: Mapped[str] = mapped_column(String(20))
    validation_report: Mapped[dict[str, Any]] = mapped_column(JSON)
    staged_rows: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LineageMixin:
    source_system: Mapped[str] = mapped_column(String(100))
    source_file_id: Mapped[str] = mapped_column(ForeignKey("source_files.id"))
    source_record_id: Mapped[str] = mapped_column(String(255))
    ingestion_run_id: Mapped[str] = mapped_column(ForeignKey("ingestion_runs.id"))
    business_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    mapping_version: Mapped[str] = mapped_column(String(50))
    validation_status: Mapped[str] = mapped_column(String(20), default="valid")
    data_origin: Mapped[str] = mapped_column(String(20))


class CustomerRow(LineageMixin, Base):
    __tablename__ = "customers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    customer_number: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(Boolean)


class SupplierRow(LineageMixin, Base):
    __tablename__ = "suppliers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    supplier_number: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(Boolean)


class ItemRow(LineageMixin, Base):
    __tablename__ = "items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    sku: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    standard_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    list_price: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    reorder_point: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    active: Mapped[bool] = mapped_column(Boolean)


class ResourceRow(LineageMixin, Base):
    __tablename__ = "resources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    resource_type: Mapped[str] = mapped_column(String(80))
    process_id: Mapped[str] = mapped_column(String(80))
    node_id: Mapped[str] = mapped_column(String(80))
    capacity_units: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class InventoryPositionRow(LineageMixin, Base):
    __tablename__ = "inventory_positions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    item_id: Mapped[str] = mapped_column(ForeignKey("items.id"))
    warehouse: Mapped[str] = mapped_column(String(80))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    __table_args__ = (UniqueConstraint("item_id", "warehouse"),)


class BalanceRow(LineageMixin, Base):
    __tablename__ = "balances"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    account_code: Mapped[str] = mapped_column(String(80), unique=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    currency: Mapped[str] = mapped_column(String(3))


class BusinessEventRow(LineageMixin, Base):
    __tablename__ = "business_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    object_id: Mapped[str] = mapped_column(String(36))
    object_type: Mapped[str] = mapped_column(String(30))
    event_type: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    state_type: Mapped[str] = mapped_column(String(10), default="actual")


class BusinessObjectRow(LineageMixin, Base):
    __tablename__ = "business_objects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    object_number: Mapped[str] = mapped_column(String(80), unique=True)
    object_type: Mapped[str] = mapped_column(String(30))
    process_id: Mapped[str] = mapped_column(String(80))
    current_node_id: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(40))
    entered_node_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    priority: Mapped[int] = mapped_column(Integer)
    state_type: Mapped[str] = mapped_column(String(10), default="actual")


class NodeStateMetricRow(Base):
    __tablename__ = "node_state_metrics"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    process_id: Mapped[str] = mapped_column(String(80))
    node_id: Mapped[str] = mapped_column(String(80))
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    object_count: Mapped[int] = mapped_column(Integer)
    total_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    total_value: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    backlog_count: Mapped[int] = mapped_column(Integer)


class StateSnapshotRow(Base):
    __tablename__ = "state_snapshots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(80))
    as_of_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_event_watermark: Mapped[str | None] = mapped_column(String(36))
    process_definition_versions: Mapped[dict[str, int]] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))


class SnapshotRecordRow(Base):
    __tablename__ = "snapshot_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("state_snapshots.id"))
    record_type: Mapped[str] = mapped_column(String(80))
    record_key: Mapped[str] = mapped_column(String(255))
    serialized_data: Mapped[dict[str, Any]] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint("snapshot_id", "record_type", "record_key"),)


# Reserved now so the migration already establishes the workstream's full SQL boundary.
class SimulationSessionRow(Base):
    __tablename__ = "simulation_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    base_snapshot_id: Mapped[str] = mapped_column(ForeignKey("state_snapshots.id"))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(String(1000), default="")
    parent_session_id: Mapped[str | None] = mapped_column(
        ForeignKey("simulation_sessions.id", name="fk_simulation_session_parent"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    state_type: Mapped[str] = mapped_column(String(10), default="simulated")


class SimulationEventRow(Base):
    __tablename__ = "simulation_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    simulation_session_id: Mapped[str] = mapped_column(ForeignKey("simulation_sessions.id"))
    event_type: Mapped[str] = mapped_column(String(80))
    effective_day: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SimulationRunRow(Base):
    __tablename__ = "simulation_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    simulation_session_id: Mapped[str] = mapped_column(ForeignKey("simulation_sessions.id"))
    snapshot_hash: Mapped[str] = mapped_column(String(64))
    process_definition_version: Mapped[str] = mapped_column(String(255))
    process_definition_hash: Mapped[str] = mapped_column(String(64))
    scenario_event_hash: Mapped[str] = mapped_column(String(64))
    horizon_days: Mapped[int] = mapped_column(Integer)
    random_seed: Mapped[int] = mapped_column(Integer)
    result_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SimulationResultRow(Base):
    __tablename__ = "simulation_results"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    simulation_run_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.id"), unique=True)
    summary_metrics: Mapped[dict[str, Any]] = mapped_column(JSON)
    event_trace: Mapped[list[dict[str, Any]]] = mapped_column(JSON)


class AccountingImpactRow(Base):
    __tablename__ = "accounting_impacts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    simulation_run_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.id"))
    event_type: Mapped[str] = mapped_column(String(80))
    object_id: Mapped[str] = mapped_column(String(36))
    simulated_hour: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    lines: Mapped[list[dict[str, Any]]] = mapped_column(JSON)


class ToolCallAuditRow(Base):
    __tablename__ = "tool_call_audit"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    agent_case_id: Mapped[str] = mapped_column(String(80))
    tool_name: Mapped[str] = mapped_column(String(80))
    argument_hash: Mapped[str] = mapped_column(String(64))
    result_reference: Mapped[str | None] = mapped_column(String(80), nullable=True)
    result_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(20))
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
