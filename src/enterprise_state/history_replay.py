from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from core.models import CanonicalModel, EnterpriseState, ProcessId, StateRecord
from core.object_schema import ObjectSchemaRegistry, load_object_schema_registry
from core.processes import ConditionDefinition, ProcessNodeDefinition, StateEffectDefinition
from core.simulation.process_runtime import RuntimeProcessCatalog, load_runtime_process_catalog

REPLAY_NAMESPACE = uuid.UUID("e52ac411-1d49-442f-a490-2192949143b0")


class ActivityInvocation(CanonicalModel):
    """One source transaction mapped to an activity in the fixed process catalog."""

    invocation_id: str = Field(min_length=1)
    process_id: ProcessId
    activity_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    occurred_at: datetime
    source_sequence: int = Field(default=0, ge=0)
    source_record_id: str = Field(min_length=1)
    bindings: dict[str, str]
    execution_inputs: dict[str, Any] = Field(default_factory=dict)
    semantic_status: Literal["confirmed", "dummy"] = "confirmed"
    mapping_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_invocation(self) -> ActivityInvocation:
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone offset")
        if "subject" not in self.bindings:
            raise ValueError("activity invocation requires a subject binding")
        return self


class ReplayResult(CanonicalModel):
    state: EnterpriseState
    invocation_ids: tuple[str, ...]


def _decimal(value: object) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("numeric state effects require finite values")
    return result


def _path_value(
    bindings: Mapping[str, StateRecord], execution_inputs: Mapping[str, Any], path: str
) -> Any:
    alias, field_name = path.split(".", 1)
    if alias == "execution":
        try:
            return execution_inputs[field_name]
        except KeyError as exc:
            raise ValueError(f"execution input does not exist: {field_name}") from exc
    try:
        return bindings[alias].data[field_name]
    except KeyError as exc:
        raise ValueError(f"state path does not exist: {path}") from exc


def _right_value(
    bindings: Mapping[str, StateRecord],
    execution_inputs: Mapping[str, Any],
    value: object | None,
    value_from: str | None,
) -> object:
    if value_from is not None:
        return _path_value(bindings, execution_inputs, value_from)
    return value


def _condition_matches(
    condition: ConditionDefinition,
    bindings: Mapping[str, StateRecord],
    execution_inputs: Mapping[str, Any],
) -> bool:
    left = _path_value(bindings, execution_inputs, condition.left)
    right = _right_value(bindings, execution_inputs, condition.value, condition.value_from)
    if condition.operator == "equals":
        return bool(left == right)
    if condition.operator == "not_equals":
        return bool(left != right)
    if condition.operator == "greater_than_or_equal":
        return _decimal(left) >= _decimal(right)
    if condition.operator == "in":
        if not isinstance(right, (tuple, list, set, frozenset)):
            raise ValueError("in condition requires a collection")
        return left in right
    raise ValueError(f"unsupported condition operator: {condition.operator}")


class HistoryReplayExecutor:
    """Deterministically replay observed transactions without invoking SimPy."""

    def __init__(
        self,
        *,
        process_directory: Path | None = None,
        process_catalog: RuntimeProcessCatalog | None = None,
        object_schemas: ObjectSchemaRegistry | None = None,
    ) -> None:
        self.processes = process_catalog or load_runtime_process_catalog(process_directory)
        self.object_schemas = object_schemas or load_object_schema_registry()

    def replay(self, state: EnterpriseState, invocations: list[ActivityInvocation]) -> ReplayResult:
        if state.state_type != "actual":
            raise ValueError("history replay requires actual EnterpriseState")
        if (
            state.process_definition_hash is not None
            and state.process_definition_hash != self.processes.content_hash
        ):
            raise ValueError("EnterpriseState and replay process definitions do not match")

        current = state
        ordered = sorted(
            invocations,
            key=lambda item: (
                item.occurred_at,
                item.source_sequence,
                item.source_record_id,
                item.invocation_id,
            ),
        )
        seen: set[str] = set()
        for invocation in ordered:
            if invocation.invocation_id in seen:
                raise ValueError(f"duplicate activity invocation: {invocation.invocation_id}")
            seen.add(invocation.invocation_id)
            current = self._apply(current, invocation)
        return ReplayResult(
            state=current,
            invocation_ids=tuple(item.invocation_id for item in ordered),
        )

    def _apply(self, state: EnterpriseState, invocation: ActivityInvocation) -> EnterpriseState:
        activity_record_id = str(
            uuid.uuid5(REPLAY_NAMESPACE, f"activity:{invocation.invocation_id}")
        )
        event_record_id = str(uuid.uuid5(REPLAY_NAMESPACE, f"event:{invocation.invocation_id}"))
        existing = {activity_record_id, event_record_id}.intersection(state.records)
        if existing == {activity_record_id, event_record_id}:
            return state
        if existing:
            raise ValueError(
                f"partial replay records exist for {invocation.invocation_id}: {sorted(existing)}"
            )

        definition = self.processes.definition(invocation.process_id)
        activity = definition.activity(invocation.activity_id)
        if activity.semantic_status != invocation.semantic_status:
            raise ValueError(
                f"semantic status mismatch for {invocation.process_id}.{invocation.activity_id}"
            )

        expected_aliases = {binding.alias for binding in activity.inputs}
        if set(invocation.bindings) != expected_aliases:
            raise ValueError(
                f"{activity.id} requires bindings {sorted(expected_aliases)}; "
                f"got {sorted(invocation.bindings)}"
            )
        required_execution = {
            name for name, spec in activity.execution_inputs.items() if spec.required
        }
        missing_execution = sorted(required_execution - set(invocation.execution_inputs))
        unknown_execution = sorted(
            set(invocation.execution_inputs) - set(activity.execution_inputs)
        )
        if missing_execution or unknown_execution:
            raise ValueError(
                f"{activity.id} execution inputs invalid; missing={missing_execution}, "
                f"unknown={unknown_execution}"
            )

        records = dict(state.records)
        bindings = {
            alias: state.record(record_id) for alias, record_id in invocation.bindings.items()
        }
        for binding in activity.inputs:
            if bindings[binding.alias].record_type != binding.object_type:
                raise ValueError(
                    f"{activity.id}.{binding.alias} expects {binding.object_type}; "
                    f"got {bindings[binding.alias].record_type}"
                )
        subject = bindings["subject"]
        current_activity = subject.data.get("current_activity_id")
        if current_activity is not None and current_activity != activity.id:
            raise ValueError(
                f"process path gap for {subject.record_id}: expected {current_activity}, "
                f"observed {activity.id}"
            )
        if not all(
            _condition_matches(condition, bindings, invocation.execution_inputs)
            for condition in activity.enabled_when
        ):
            raise ValueError(f"activity preconditions are not met: {activity.id}")

        changes: dict[str, dict[str, dict[str, Any]]] = {}
        version_increment = 0
        for effect in activity.operations:
            record, field_name, before, after = self._apply_effect(
                records, bindings, invocation.execution_inputs, effect
            )
            records[record.record_id] = record
            bindings = {alias: records[value.record_id] for alias, value in bindings.items()}
            if before != after:
                changes.setdefault(record.record_id, {})[field_name] = {
                    "before": before,
                    "after": after,
                }
                version_increment += 1

        next_activity = self._next_activity(activity, bindings, invocation.execution_inputs)
        if next_activity is not None:
            subject = records[subject.record_id]
            before = subject.data.get("current_activity_id")
            subject = self._updated_record(subject, "current_activity_id", next_activity)
            records[subject.record_id] = subject
            bindings["subject"] = subject
            if before != next_activity:
                changes.setdefault(subject.record_id, {})["current_activity_id"] = {
                    "before": before,
                    "after": next_activity,
                }
                version_increment += 1

        references = tuple(bindings[alias].record_id for alias in activity.on_complete.references)
        records[activity_record_id] = StateRecord(
            record_id=activity_record_id,
            record_kind="activity_run",
            record_type=activity.id,
            project_id=state.project_id,
            data={
                "process_id": invocation.process_id,
                "activity_id": activity.id,
                "subject_record_id": subject.record_id,
                "status": "completed",
                "occurred_at": invocation.occurred_at,
                "source_record_id": invocation.source_record_id,
                "mapping_version": invocation.mapping_version,
                "semantic_status": invocation.semantic_status,
                "execution_inputs": invocation.execution_inputs,
            },
            references=tuple(invocation.bindings.values()),
            state_type="actual",
        )
        records[event_record_id] = StateRecord(
            record_id=event_record_id,
            record_kind="event",
            record_type=activity.on_complete.event_type,
            project_id=state.project_id,
            data={
                "process_id": invocation.process_id,
                "activity_id": activity.id,
                "occurred_at": invocation.occurred_at,
                "source_record_id": invocation.source_record_id,
                "mapping_version": invocation.mapping_version,
                "semantic_status": invocation.semantic_status,
                "changes": changes,
            },
            references=references,
            state_type="actual",
        )
        version_increment += 2
        updated_state = state.model_copy(
            update={
                "records": dict(sorted(records.items())),
                "state_version": state.state_version + version_increment,
                "as_of_time": max(filter(None, (state.as_of_time, invocation.occurred_at))),
                "process_definition_hash": self.processes.content_hash,
            },
            deep=True,
        )
        for record in bindings.values():
            self.object_schemas.validate_record(updated_state.record(record.record_id))
        return updated_state

    @staticmethod
    def _updated_record(record: StateRecord, field_name: str, value: Any) -> StateRecord:
        if record.data.get(field_name) == value:
            return record
        data = dict(record.data)
        data[field_name] = value
        return record.model_copy(update={"data": data, "version": record.version + 1})

    def _apply_effect(
        self,
        records: dict[str, StateRecord],
        bindings: Mapping[str, StateRecord],
        execution_inputs: Mapping[str, Any],
        effect: StateEffectDefinition,
    ) -> tuple[StateRecord, str, Any, Any]:
        alias, field_name = effect.target.split(".", 1)
        record = records[bindings[alias].record_id]
        before = record.data.get(field_name)
        value = _right_value(bindings, execution_inputs, effect.value, effect.value_from)
        if effect.operation == "set":
            after = value
        elif effect.operation == "increase":
            after = _decimal(before or 0) + _decimal(value)
        else:
            after = _decimal(before or 0) - _decimal(value)
            if effect.wait_if_insufficient and after < 0:
                raise ValueError(f"insufficient value for historical effect {effect.target}")
        updated = self._updated_record(record, field_name, after)
        return updated, field_name, before, after

    @staticmethod
    def _next_activity(
        activity: ProcessNodeDefinition,
        bindings: Mapping[str, StateRecord],
        execution_inputs: Mapping[str, Any],
    ) -> str | None:
        matches = [
            transition.target
            for transition in activity.next
            if all(
                _condition_matches(condition, bindings, execution_inputs)
                for condition in transition.conditions
            )
        ]
        if len(matches) > 1:
            raise ValueError(f"multiple transitions matched after activity {activity.id}")
        if not matches:
            if activity.next:
                raise ValueError(f"no transition matched after activity {activity.id}")
            return None
        return matches[0]
