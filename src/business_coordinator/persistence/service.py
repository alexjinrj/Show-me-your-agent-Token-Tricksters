from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from business_coordinator.domain.models import SnapshotBundle, SnapshotManifest, SnapshotRecord
from business_coordinator.ingestion.csv_ingestion import (
    SourceInspection,
    ValidationReport,
    inspect_csv,
    parse_and_validate,
)
from business_coordinator.persistence.models import (
    BalanceRow,
    BusinessEventRow,
    BusinessObjectRow,
    CustomerRow,
    IngestionRunRow,
    InventoryPositionRow,
    ItemRow,
    ResourceRow,
    SnapshotRecordRow,
    SourceFileRow,
    StateSnapshotRow,
    SupplierRow,
)

NAMESPACE = uuid.UUID("02dd49ce-1c5f-4efc-9678-7ad4e30fbfc5")


def _id(*parts: object) -> str:
    return str(uuid.uuid5(NAMESPACE, ":".join(str(part) for part in parts)))


def _json_default(value: object) -> str:
    if isinstance(value, (datetime, Decimal)):
        return str(value)
    raise TypeError(f"cannot encode {type(value)!r}")


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=_json_default)


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode()).hexdigest()


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ActualStateService:
    def __init__(self, engine: Engine, *, source_system: str = "demo") -> None:
        self.engine = engine
        self.source_system = source_system

    def inspect_csv(self, path: str | Path) -> SourceInspection:
        return inspect_csv(path)

    def validate_csv(
        self, path: str | Path, source_type: str, mapping_version: str
    ) -> tuple[str, ValidationReport]:
        inspection = inspect_csv(path)
        report = parse_and_validate(path, source_type, mapping_version)
        now = _utcnow()
        source_file_id = _id("source-file", inspection.sha256)
        run_id = _id("ingestion-run", inspection.sha256, source_type, mapping_version)
        with Session(self.engine) as session, session.begin():
            source = session.get(SourceFileRow, source_file_id)
            if source is None:
                session.add(
                    SourceFileRow(
                        id=source_file_id,
                        source_system=self.source_system,
                        file_name=Path(path).name,
                        sha256=inspection.sha256,
                        row_count=inspection.row_count,
                        created_at=now,
                    )
                )
            run = session.get(IngestionRunRow, run_id)
            serialized_rows = json.loads(_canonical_json(report.rows))
            serialized_report = json.loads(_canonical_json(report.model_dump(exclude={"rows"})))
            if run is None:
                session.add(
                    IngestionRunRow(
                        id=run_id,
                        source_file_id=source_file_id,
                        source_type=source_type,
                        mapping_version=mapping_version,
                        validation_status="validated" if report.valid else "rejected",
                        validation_report=serialized_report,
                        staged_rows=serialized_rows,
                        idempotency_key=None,
                        created_at=now,
                        committed_at=None,
                    )
                )
        return run_id, report

    def commit_ingestion(self, validated_run_id: str, idempotency_key: str) -> dict[str, Any]:
        with Session(self.engine) as session, session.begin():
            existing = session.scalar(
                select(IngestionRunRow).where(IngestionRunRow.idempotency_key == idempotency_key)
            )
            if existing is not None:
                return {"ingestion_run_id": existing.id, "committed": False, "duplicate": True}
            run = session.get(IngestionRunRow, validated_run_id)
            if run is None:
                raise ValueError("ingestion run does not exist")
            if run.validation_status != "validated":
                raise ValueError("only a fully validated ingestion may be committed")
            if run.committed_at is not None:
                return {"ingestion_run_id": run.id, "committed": False, "duplicate": True}
            source = session.get(SourceFileRow, run.source_file_id)
            if source is None:
                raise RuntimeError("source file lineage is missing")
            now = _utcnow()
            for row in run.staged_rows:
                self._commit_row(session, run, source, row, now)
            run.idempotency_key = idempotency_key
            run.validation_status = "committed"
            run.committed_at = now
            return {
                "ingestion_run_id": run.id,
                "committed": True,
                "duplicate": False,
                "row_count": len(run.staged_rows),
            }

    def _lineage(
        self, run: IngestionRunRow, source: SourceFileRow, row: dict[str, Any], now: datetime
    ) -> dict[str, Any]:
        timestamp = (
            row.get("business_timestamp") or row.get("order_date") or row.get("effective_at")
        )
        if not isinstance(timestamp, str):
            raise ValueError("lineage requires a business timestamp")
        return {
            "source_system": source.source_system,
            "source_file_id": source.id,
            "source_record_id": row["source_record_id"],
            "ingestion_run_id": run.id,
            "business_timestamp": datetime.fromisoformat(timestamp),
            "ingested_at": now,
            "mapping_version": run.mapping_version,
            "validation_status": "valid",
            "data_origin": row["data_origin"],
        }

    def _commit_row(
        self,
        session: Session,
        run: IngestionRunRow,
        source: SourceFileRow,
        row: dict[str, Any],
        now: datetime,
    ) -> None:
        lineage = self._lineage(run, source, row, now)
        kind = run.source_type
        if kind == "customers":
            session.add(
                CustomerRow(
                    id=_id("customer", row["customer_number"]),
                    customer_number=row["customer_number"],
                    name=row["name"],
                    active=row["active"],
                    **lineage,
                )
            )
        elif kind == "suppliers":
            session.add(
                SupplierRow(
                    id=_id("supplier", row["supplier_number"]),
                    supplier_number=row["supplier_number"],
                    name=row["name"],
                    active=row["active"],
                    **lineage,
                )
            )
        elif kind == "items":
            session.add(
                ItemRow(
                    id=_id("item", row["sku"]),
                    sku=row["sku"],
                    name=row["name"],
                    standard_cost=Decimal(row["standard_cost"]),
                    list_price=Decimal(row["list_price"]),
                    reorder_point=Decimal(row["reorder_point"]),
                    active=row["active"],
                    **lineage,
                )
            )
        elif kind == "resources":
            session.add(
                ResourceRow(
                    id=_id("resource", row["resource_type"], row["node_id"]),
                    resource_type=row["resource_type"],
                    process_id=row["process_id"],
                    node_id=row["node_id"],
                    capacity_units=Decimal(row["capacity_units"]),
                    effective_at=datetime.fromisoformat(row["effective_at"]),
                    **lineage,
                )
            )
        elif kind == "inventory":
            item_id = self._require_item(session, row["sku"])
            object_id = _id("inventory", row["sku"], row["warehouse"])
            session.add(
                InventoryPositionRow(
                    id=object_id,
                    item_id=item_id,
                    warehouse=row["warehouse"],
                    quantity=Decimal(row["quantity"]),
                    **lineage,
                )
            )
            self._add_event(
                session, run, source, row, now, object_id, "inventory", "inventory_opened"
            )
        elif kind == "opening_balances":
            object_id = _id("balance", row["account_code"])
            session.add(
                BalanceRow(
                    id=object_id,
                    account_code=row["account_code"],
                    amount=Decimal(row["amount"]),
                    currency=row["currency"],
                    **lineage,
                )
            )
            self._add_event(session, run, source, row, now, object_id, "balance", "balance_opened")
        elif kind in {"sales_orders", "purchase_orders"}:
            self._commit_order(session, run, source, row, now)
        else:
            raise ValueError(f"unsupported source type: {kind}")

    def _require_item(self, session: Session, sku: str) -> str:
        item_id = session.scalar(select(ItemRow.id).where(ItemRow.sku == sku))
        if item_id is None:
            raise ValueError(f"unknown SKU: {sku}")
        return item_id

    def _commit_order(
        self,
        session: Session,
        run: IngestionRunRow,
        source: SourceFileRow,
        row: dict[str, Any],
        now: datetime,
    ) -> None:
        is_sales = run.source_type == "sales_orders"
        party_column = "customer_number" if is_sales else "supplier_number"
        if is_sales:
            party_id = session.scalar(
                select(CustomerRow.id).where(CustomerRow.customer_number == row[party_column])
            )
        else:
            party_id = session.scalar(
                select(SupplierRow.id).where(SupplierRow.supplier_number == row[party_column])
            )
        if party_id is None:
            raise ValueError(f"unknown party: {row[party_column]}")
        self._require_item(session, row["sku"])
        object_type = "sales_order" if is_sales else "purchase_order"
        process_id = "order_to_cash" if is_sales else "procure_to_pay"
        price_field = "unit_price" if is_sales else "unit_cost"
        object_id = _id(object_type, row["order_number"])
        quantity = Decimal(row["quantity"])
        amount = quantity * Decimal(row[price_field])
        status = row["status"]
        node_map = {
            "open": "order_received" if is_sales else "purchase_order_placed",
            "backlog": "pick_and_pack",
            "shipped": "shipped",
            "paid": "paid" if is_sales else "supplier_paid",
            "received": "goods_received",
        }
        session.add(
            BusinessObjectRow(
                id=object_id,
                object_number=row["order_number"],
                object_type=object_type,
                process_id=process_id,
                current_node_id=node_map[status],
                status=status,
                entered_node_at=datetime.fromisoformat(row["order_date"]),
                amount=amount,
                quantity=quantity,
                priority=int(row["priority"]),
                state_type="actual",
                **self._lineage(run, source, row, now),
            )
        )
        self._add_event(
            session, run, source, row, now, object_id, object_type, f"{object_type}_imported"
        )

    def _add_event(
        self,
        session: Session,
        run: IngestionRunRow,
        source: SourceFileRow,
        row: dict[str, Any],
        now: datetime,
        object_id: str,
        object_type: str,
        event_type: str,
    ) -> None:
        event_id = _id("event", run.id, row["source_record_id"])
        session.add(
            BusinessEventRow(
                id=event_id,
                object_id=object_id,
                object_type=object_type,
                event_type=event_type,
                payload=row,
                state_type="actual",
                **self._lineage(run, source, row, now),
            )
        )

    def actual_state_hash(self) -> str:
        return _hash(self._snapshot_content())

    def _snapshot_content(self, as_of_time: datetime | None = None) -> list[dict[str, Any]]:
        lineage_fields = (
            "source_system",
            "source_file_id",
            "source_record_id",
            "ingestion_run_id",
            "business_timestamp",
            "mapping_version",
            "validation_status",
            "data_origin",
        )
        specs: list[tuple[str, type[Any], str, tuple[str, ...]]] = [
            (
                "customer",
                CustomerRow,
                "customer_number",
                ("customer_number", "name", "active") + lineage_fields,
            ),
            (
                "supplier",
                SupplierRow,
                "supplier_number",
                ("supplier_number", "name", "active") + lineage_fields,
            ),
            (
                "item",
                ItemRow,
                "sku",
                ("sku", "name", "standard_cost", "list_price", "reorder_point", "active")
                + lineage_fields,
            ),
            (
                "resource",
                ResourceRow,
                "id",
                ("resource_type", "process_id", "node_id", "capacity_units", "effective_at")
                + lineage_fields,
            ),
            (
                "inventory",
                InventoryPositionRow,
                "id",
                ("item_id", "warehouse", "quantity") + lineage_fields,
            ),
            (
                "balance",
                BalanceRow,
                "account_code",
                ("account_code", "amount", "currency") + lineage_fields,
            ),
            (
                "business_object",
                BusinessObjectRow,
                "object_number",
                (
                    "id",
                    "object_number",
                    "object_type",
                    "process_id",
                    "current_node_id",
                    "status",
                    "entered_node_at",
                    "amount",
                    "quantity",
                    "priority",
                    "state_type",
                )
                + lineage_fields,
            ),
        ]
        records: list[dict[str, Any]] = []
        with Session(self.engine) as session:
            for record_type, model, key_name, fields in specs:
                statement = select(model)
                if as_of_time is not None and hasattr(model, "business_timestamp"):
                    statement = statement.where(model.business_timestamp <= as_of_time)
                rows = session.scalars(statement).all()
                for row in rows:
                    records.append(
                        {
                            "record_type": record_type,
                            "record_key": str(getattr(row, key_name)),
                            "data": {field: getattr(row, field) for field in fields},
                        }
                    )
        records.sort(key=lambda value: (value["record_type"], value["record_key"]))
        return cast(list[dict[str, Any]], json.loads(_canonical_json(records)))

    def create_snapshot(
        self, as_of_time: datetime, company_id: str = "SG-SME-001"
    ) -> SnapshotManifest:
        if as_of_time.tzinfo is None:
            raise ValueError("as_of_time must be timezone-aware")
        records = self._snapshot_content(as_of_time)
        content_hash = _hash(records)
        snapshot_id = _id("snapshot", company_id, as_of_time.isoformat(), content_hash)
        created_at = _utcnow()
        with Session(self.engine) as session, session.begin():
            existing = session.get(StateSnapshotRow, snapshot_id)
            if existing is None:
                watermark = session.scalar(select(func.max(BusinessEventRow.id)))
                snapshot = StateSnapshotRow(
                    id=snapshot_id,
                    company_id=company_id,
                    as_of_time=as_of_time,
                    created_at=created_at,
                    source_event_watermark=watermark,
                    process_definition_versions={"order_to_cash": 1, "procure_to_pay": 1},
                    content_hash=content_hash,
                )
                session.add(snapshot)
                session.flush()
                for record in records:
                    session.add(
                        SnapshotRecordRow(
                            id=_id(
                                "snapshot-record",
                                snapshot_id,
                                record["record_type"],
                                record["record_key"],
                            ),
                            snapshot_id=snapshot_id,
                            record_type=record["record_type"],
                            record_key=record["record_key"],
                            serialized_data=record["data"],
                        )
                    )
            else:
                created_at = existing.created_at.replace(tzinfo=UTC)
        return self.load_snapshot(snapshot_id).manifest

    def load_snapshot(self, snapshot_id: str) -> SnapshotBundle:
        with Session(self.engine) as session:
            snapshot = session.get(StateSnapshotRow, snapshot_id)
            if snapshot is None:
                raise ValueError("snapshot does not exist")
            rows = session.scalars(
                select(SnapshotRecordRow)
                .where(SnapshotRecordRow.snapshot_id == snapshot_id)
                .order_by(SnapshotRecordRow.record_type, SnapshotRecordRow.record_key)
            ).all()
            manifest = SnapshotManifest(
                snapshot_id=snapshot.id,
                company_id=snapshot.company_id,
                as_of_time=snapshot.as_of_time.replace(tzinfo=UTC),
                created_at=snapshot.created_at.replace(tzinfo=UTC),
                source_event_watermark=snapshot.source_event_watermark,
                process_definition_versions=dict(snapshot.process_definition_versions),
                content_hash=snapshot.content_hash,
                state_type="actual",
            )
            record_data = tuple(
                SnapshotRecord(
                    record_type=row.record_type,
                    record_key=row.record_key,
                    data=json.loads(_canonical_json(row.serialized_data)),
                )
                for row in rows
            )
        return SnapshotBundle(manifest=manifest, records=record_data)

    def counts(self) -> dict[str, int]:
        models = {
            "customers": CustomerRow,
            "suppliers": SupplierRow,
            "items": ItemRow,
            "resources": ResourceRow,
            "inventory": InventoryPositionRow,
            "balances": BalanceRow,
            "business_events": BusinessEventRow,
            "business_objects": BusinessObjectRow,
        }
        with Session(self.engine) as session:
            return {
                name: session.scalar(select(func.count()).select_from(model)) or 0
                for name, model in models.items()
            }


def commit_demo_files(service: ActualStateService, files: Iterable[tuple[str, Path]]) -> None:
    for source_type, path in files:
        run_id, report = service.validate_csv(path, source_type, "adventureworks-v1")
        if not report.valid:
            raise ValueError(f"invalid demo file {path}: {report.issues}")
        service.commit_ingestion(run_id, f"demo:{source_type}:{service.inspect_csv(path).sha256}")
