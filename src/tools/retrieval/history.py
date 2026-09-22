from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from core.models import EnterpriseState, StateRecord
from tools.retrieval.contracts import History


class EnterpriseHistoryError(ValueError):
    """Raised when a bounded object-history request cannot be answered safely."""


def _date_value(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EnterpriseHistoryError("as_of must be an ISO date or timestamp") from exc
    if parsed.tzinfo is None:
        if len(value) != 10:
            raise EnterpriseHistoryError("Timestamp as_of requires a timezone offset")
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _record_time(record: StateRecord) -> datetime | None:
    for field in ("occurred_at", "completed_at", "started_at"):
        value = record.data.get(field)
        if value is not None:
            if isinstance(value, datetime):
                if value.tzinfo is None or value.utcoffset() is None:
                    raise EnterpriseHistoryError(
                        f"Record {record.record_id} has a timezone-naive {field}"
                    )
                return value.astimezone(UTC)
            return _date_value(str(value))
    return None


def _resolve_object(state: EnterpriseState, object_type: str, object_id: str) -> StateRecord:
    matches = []
    for record in state.objects(object_type):
        identifiers = {
            record.record_id,
            str(record.data.get("id", "")),
            str(record.data.get("object_number", "")),
            str(record.data.get("sku", "")),
        }
        if object_id in identifiers:
            matches.append(record)
    if not matches:
        raise EnterpriseHistoryError(
            f"No {object_type} object matches {object_id!r} in this Enterprise State"
        )
    if len(matches) > 1:
        raise EnterpriseHistoryError(
            f"Object identifier {object_id!r} is ambiguous for {object_type}"
        )
    return matches[0]


def _project_object(record: StateRecord, fields: list[str]) -> dict[str, Any]:
    selected = fields or [
        field
        for field in (
            "object_number",
            "status",
            "current_activity_id",
            "sku",
            "warehouse_id",
            "quantity",
            "quantity_on_hand",
            "quantity_reserved",
            "quantity_available",
            "amount",
            "due_at",
        )
        if field in record.data
    ]
    unknown = sorted(set(selected) - set(record.data))
    if unknown:
        raise EnterpriseHistoryError(f"Unknown object fields requested: {unknown}")
    return {
        "record_id": record.record_id,
        "record_type": record.record_type,
        "record_version": record.version,
        "data": {field: deepcopy(record.data[field]) for field in selected},
    }


def _timeline_item(record: StateRecord) -> dict[str, Any]:
    occurred_at = _record_time(record)
    item: dict[str, Any] = {
        "record_id": record.record_id,
        "record_kind": record.record_kind,
        "record_type": record.record_type,
        "occurred_at": occurred_at,
        "references": record.references,
    }
    for field in (
        "process_id",
        "activity_id",
        "status",
        "semantic_status",
        "source_record_id",
        "mapping_version",
        "changes",
    ):
        if field in record.data:
            item[field] = deepcopy(record.data[field])
    return item


def _reverse_to_time(
    state: EnterpriseState,
    subject: StateRecord,
    events: list[StateRecord],
    cutoff: datetime,
) -> tuple[dict[str, Any] | None, str, list[str]]:
    if state.as_of_time is None:
        return None, "unavailable", ["Enterprise State has no as_of_time"]
    if cutoff > state.as_of_time:
        raise EnterpriseHistoryError("as_of cannot be later than the Enterprise State")
    if cutoff == state.as_of_time:
        return (
            deepcopy(subject.data),
            "current_projection",
            ["Timeline includes only imported or mapped records; full history is not guaranteed"],
        )

    missing_time = [event.record_id for event in events if _record_time(event) is None]
    if missing_time:
        return (
            None,
            "unavailable",
            [f"Related events have no usable occurred_at: {missing_time[:3]}"],
        )

    future = [event for event in events if (_record_time(event) or cutoff) > cutoff]
    if not future:
        return (
            None,
            "unavailable",
            ["No reversible event evidence covers the requested historical point"],
        )

    data = deepcopy(subject.data)
    warnings: list[str] = []
    for event in sorted(
        future,
        key=lambda record: (_record_time(record) or cutoff, record.record_id),
        reverse=True,
    ):
        changes = event.data.get("changes")
        if not isinstance(changes, dict):
            warnings.append(f"Event {event.record_id} has no reversible change set")
            continue
        object_changes = changes.get(subject.record_id, {})
        if not isinstance(object_changes, dict):
            warnings.append(f"Event {event.record_id} has an invalid change set")
            continue
        for field, change in object_changes.items():
            if not isinstance(change, dict) or "before" not in change or "after" not in change:
                warnings.append(f"Event {event.record_id} has an invalid change for {field}")
                continue
            data[field] = deepcopy(change["before"])

    if warnings:
        return None, "unavailable", warnings
    return data, "reconstructed", []


def query_enterprise_history(state: EnterpriseState, request: History) -> dict[str, Any]:
    """Return a bounded object timeline and reconstruct state only from reversible evidence."""

    cutoff = _date_value(request.as_of)
    subject = _resolve_object(state, request.object_type, request.object_id)
    related = [
        record
        for record in state.records.values()
        if record.record_kind in {"event", "activity_run"}
        and (
            subject.record_id in record.references
            or record.data.get("subject_record_id") == subject.record_id
        )
    ]
    events = [record for record in related if record.record_kind == "event"]
    visible = [
        record
        for record in related
        if (timestamp := _record_time(record)) is not None and timestamp <= cutoff
    ]
    visible.sort(key=lambda record: (_record_time(record), record.record_kind, record.record_id))
    page = visible[request.offset : request.offset + request.limit]
    reconstructed, status, warnings = _reverse_to_time(state, subject, events, cutoff)

    projected = _project_object(subject, request.fields)
    if reconstructed is not None:
        projected["data"] = {
            field: deepcopy(reconstructed[field])
            for field in projected["data"]
            if field in reconstructed
        }

    total = len(visible)
    return {
        "query": request.model_dump(mode="json"),
        "enterprise_state_reference": state.scope_id,
        "enterprise_state_as_of": state.as_of_time,
        "object": projected if reconstructed is not None else None,
        "current_object_projection": _project_object(subject, request.fields),
        "reconstruction_status": status,
        "timeline": [_timeline_item(record) for record in page],
        "total_timeline_records": total,
        "returned": len(page),
        "next_offset": request.offset + len(page)
        if request.offset + len(page) < total
        else None,
        "coverage": (
            "Current projection is authoritative at Enterprise State as_of_time"
            if status == "current_projection"
            else "Historical state is returned only when every later related event has a "
            "reversible before/after change set"
        ),
        "completeness": {
            "current_projection": "current_projection_only",
            "reconstructed": "complete_for_recorded_reversible_events",
            "unavailable": "unavailable",
        }[status],
        "warnings": warnings,
    }
