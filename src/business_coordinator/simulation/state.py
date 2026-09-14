from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal, cast

from business_coordinator.domain.models import (
    ActivityRunStatus,
    EnterpriseState,
    SnapshotBundle,
    StateRecord,
    StateRecordChange,
)
from business_coordinator.domain.serialization import canonical_hash

ACTIVITY_ID_MIGRATION = {
    "order_received": "receive_order",
    "credit_review": "review_credit",
    "order_approved": "approve_order",
    "inventory_allocated": "allocate_inventory",
    "shipped": "ship_goods",
    "invoiced": "record_customer_invoice",
    "paid": "collect_customer_payment",
    "reorder_triggered": "evaluate_reorder",
    "purchase_order_placed": "place_purchase_order",
    "supplier_lead_time": "wait_for_supplier_delivery",
    "goods_received": "receive_goods",
    "supplier_invoice_recorded": "record_supplier_invoice",
    "supplier_paid": "pay_supplier",
}


def _decimal(value: object) -> Decimal:
    return Decimal(str(value))


@dataclass
class SimulationState:
    """Mutable runtime store that publishes immutable EnterpriseState versions."""

    scope_id: str
    project_id: str
    records: dict[str, StateRecord]
    state_version: int = 0
    _pending_changes: list[StateRecordChange] = field(default_factory=list)
    _pending_event_ids: list[str] = field(default_factory=list)
    _event_sequence: int = 0
    _activity_sequence: int = 0

    def records_of_type(self, record_type: str) -> list[StateRecord]:
        return sorted(
            (record for record in self.records.values() if record.record_type == record_type),
            key=lambda record: record.record_id,
        )

    def records_of_kind(self, record_kind: str) -> list[StateRecord]:
        return sorted(
            (record for record in self.records.values() if record.record_kind == record_kind),
            key=lambda record: record.record_id,
        )

    def record(self, record_id: str) -> StateRecord:
        try:
            return self.records[record_id]
        except KeyError as exc:
            raise ValueError(f"state record does not exist: {record_id}") from exc

    def related(self, object_type: str, match_field: str, value: object) -> StateRecord:
        matches = [
            record
            for record in self.records_of_type(object_type)
            if record.data.get(match_field) == value
        ]
        if len(matches) != 1:
            raise ValueError(
                f"expected one {object_type} where {match_field}={value!r}; found {len(matches)}"
            )
        return matches[0]

    def update(self, record_id: str, field_name: str, value: Any) -> StateRecord:
        current = self.record(record_id)
        before = current.data.get(field_name)
        if before == value:
            return current
        data = deepcopy(current.data)
        data[field_name] = value
        updated = current.model_copy(update={"data": data, "version": current.version + 1})
        self.records[record_id] = updated
        self.state_version += 1
        self._pending_changes.append(
            StateRecordChange(
                record_id=record_id,
                record_kind=current.record_kind,
                record_type=current.record_type,
                operation="updated",
                changed_fields={field_name: {"before": before, "after": value}},
            )
        )
        return updated

    def create_record(self, record: StateRecord) -> StateRecord:
        if record.record_id in self.records:
            raise ValueError(f"state record already exists: {record.record_id}")
        self.records[record.record_id] = record
        self.state_version += 1
        self._pending_changes.append(
            StateRecordChange(
                record_id=record.record_id,
                record_kind=record.record_kind,
                record_type=record.record_type,
                operation="created",
                changed_fields=deepcopy(record.data),
            )
        )
        if record.record_kind == "event":
            self._pending_event_ids.append(record.record_id)
        return record

    def append_event(
        self,
        event_type: str,
        references: tuple[str, ...],
        simulated_hour: Decimal,
        data: dict[str, Any] | None = None,
    ) -> StateRecord:
        self._event_sequence += 1
        return self.create_record(
            StateRecord(
                record_id=f"event:{self._event_sequence:08d}",
                record_kind="event",
                record_type=event_type,
                project_id=self.project_id,
                data={"simulated_hour": simulated_hour, **(data or {})},
                references=references,
            )
        )

    def start_activity(
        self,
        process_id: str,
        activity_id: str,
        subject_record_id: str,
        references: tuple[str, ...],
        simulated_hour: Decimal,
    ) -> str:
        self._activity_sequence += 1
        record_id = (
            f"activity_run:{process_id}:{activity_id}:"
            f"{subject_record_id}:{self._activity_sequence:08d}"
        )
        self.create_record(
            StateRecord(
                record_id=record_id,
                record_kind="activity_run",
                record_type=activity_id,
                project_id=self.project_id,
                data={
                    "process_id": process_id,
                    "activity_id": activity_id,
                    "subject_record_id": subject_record_id,
                    "status": "waiting",
                    "started_hour": simulated_hour,
                },
                references=references,
            )
        )
        return record_id

    def complete_activity(self, record_id: str, simulated_hour: Decimal) -> None:
        self.update(record_id, "status", "completed")
        self.update(record_id, "completed_hour", simulated_hour)

    def mark_activity_running(self, record_id: str, simulated_hour: Decimal) -> None:
        self.update(record_id, "status", "running")
        self.update(record_id, "started_hour", simulated_hour)

    def enterprise_state(self, simulated_hour: Decimal) -> EnterpriseState:
        return EnterpriseState(
            scope_id=self.scope_id,
            project_id=self.project_id,
            state_version=self.state_version,
            simulated_hour=simulated_hour,
            records=dict(self.records),
        )

    def state_hash(self, simulated_hour: Decimal) -> str:
        return canonical_hash(self.enterprise_state(simulated_hour))

    def active_activities(self) -> tuple[ActivityRunStatus, ...]:
        return tuple(
            ActivityRunStatus(
                activity_id=str(record.data["activity_id"]),
                subject_record_id=str(record.data["subject_record_id"]),
                status=cast(Literal["waiting", "running", "completed"], record.data["status"]),
            )
            for record in self.records_of_kind("activity_run")
            if record.data.get("status") in {"waiting", "running"}
        )

    def drain_checkpoint_changes(
        self,
    ) -> tuple[tuple[StateRecordChange, ...], tuple[str, ...]]:
        changes = tuple(self._pending_changes)
        event_ids = tuple(self._pending_event_ids)
        self._pending_changes.clear()
        self._pending_event_ids.clear()
        return changes, event_ids

    @property
    def item_costs(self) -> dict[str, Decimal]:
        return {
            str(record.data["sku"]): _decimal(record.data["standard_cost"])
            for record in self.records_of_type("item")
        }

    @property
    def item_prices(self) -> dict[str, Decimal]:
        return {
            str(record.data["sku"]): _decimal(record.data["list_price"])
            for record in self.records_of_type("item")
        }

    @property
    def resource_capacities(self) -> dict[str, int]:
        capacities: dict[str, int] = {}
        for record in self.records_of_type("resource_capacity"):
            resource_type = str(record.data["resource_type"])
            capacity = max(1, int(_decimal(record.data["capacity_units"])))
            capacities[resource_type] = max(capacities.get(resource_type, 0), capacity)
        return capacities

    def balance(self, account_code: str) -> Decimal:
        record = self.related("balance", "account_code", account_code)
        return _decimal(record.data["amount"])


def snapshot_to_state(snapshot: SnapshotBundle) -> SimulationState:
    """Convert an immutable snapshot into an isolated object-centric state store."""
    source_records = [deepcopy(record.model_dump(mode="python")) for record in snapshot.records]
    items_by_id: dict[str, dict[str, Any]] = {}
    for record in source_records:
        if record["record_type"] == "item":
            items_by_id[str(record["data"]["id"])] = record["data"]

    records: dict[str, StateRecord] = {}
    for source in source_records:
        source_type = str(source["record_type"])
        source_key = str(source["record_key"])
        data = source["data"]
        record_type = source_type
        record_id = f"{source_type}:{source_key}"
        record_kind: Literal["object", "event"] = (
            "event" if source_type == "business_event" else "object"
        )

        if source_type == "inventory":
            item = items_by_id[str(data["item_id"])]
            sku = str(item["sku"])
            record_type = "inventory_position"
            record_id = f"inventory_position:{sku}:main"
            quantity = _decimal(data["quantity"])
            data = {
                **data,
                "sku": sku,
                "warehouse_id": str(data.get("warehouse", "main")),
                "quantity_on_hand": quantity,
                "quantity_reserved": Decimal("0"),
                "quantity_available": quantity,
            }
        elif source_type == "resource":
            record_type = "resource_capacity"
        elif source_type == "business_object":
            details = data.get("details", {})
            record_type = str(data["object_type"])
            record_id = str(data["id"])
            data = {
                **data,
                "sku": str(details.get("sku", "")),
                "due_at": details.get("due_date", data["entered_node_at"]),
                "current_activity_id": ACTIVITY_ID_MIGRATION.get(
                    str(data["current_node_id"]), str(data["current_node_id"])
                ),
            }
        records[record_id] = StateRecord(
            record_id=record_id,
            record_kind=record_kind,
            record_type=record_type,
            project_id=snapshot.manifest.company_id,
            data=data,
            state_type="simulated",
        )

    state = SimulationState(
        scope_id=snapshot.manifest.snapshot_id,
        project_id=snapshot.manifest.company_id,
        records=records,
    )
    missing_skus = sorted(
        str(record.data["object_number"])
        for object_type in ("sales_order", "purchase_order")
        for record in state.records_of_type(object_type)
        if not record.data.get("sku")
    )
    if missing_skus:
        raise ValueError(f"snapshot business objects are missing SKU details: {missing_skus[:3]}")
    required_balances = {"CASH", "ACCOUNTS_RECEIVABLE", "ACCOUNTS_PAYABLE"}
    available_balances = {
        str(record.data["account_code"]) for record in state.records_of_type("balance")
    }
    missing_balances = sorted(required_balances - available_balances)
    if missing_balances:
        raise ValueError(f"snapshot is missing opening balances: {missing_balances}")
    required_resources = {"sales_staff", "warehouse_staff", "finance_staff", "purchasing_staff"}
    missing_resources = sorted(required_resources - state.resource_capacities.keys())
    if missing_resources:
        raise ValueError(f"snapshot is missing resource capacity: {missing_resources}")
    state.drain_checkpoint_changes()
    return state
