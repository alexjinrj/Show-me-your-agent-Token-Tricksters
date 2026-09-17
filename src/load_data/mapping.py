from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import Field, model_validator

from core.models import CanonicalModel, EnterpriseState, ProcessId, StateRecord
from core.object_schema import ObjectSchemaRegistry
from enterprise_state.history_replay import ActivityInvocation

TransformName = Literal["string", "decimal", "integer", "boolean", "datetime"]


class FieldMapping(CanonicalModel):
    source: str = Field(min_length=1)
    transform: TransformName = "string"
    default: Any | None = None


class ObjectMappingSpec(CanonicalModel):
    mapping_type: Literal["object_snapshot"] = "object_snapshot"
    mapping_version: str = Field(min_length=1)
    target_object_type: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    identity: tuple[str, ...] = Field(min_length=1)
    attributes: dict[str, FieldMapping]
    as_of: FieldMapping

    @model_validator(mode="after")
    def identity_is_mapped(self) -> ObjectMappingSpec:
        missing = sorted(set(self.identity) - set(self.attributes))
        if missing:
            raise ValueError(f"identity fields are not mapped: {missing}")
        return self


class BindingMapping(CanonicalModel):
    object_type: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    lookup: dict[str, str] = Field(min_length=1)


class ActivityMappingSpec(CanonicalModel):
    mapping_type: Literal["activity_invocation"] = "activity_invocation"
    mapping_version: str = Field(min_length=1)
    process_id: ProcessId
    activity_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    semantic_status: Literal["confirmed", "dummy"] = "confirmed"
    source_record_id: str = Field(min_length=1)
    source_sequence: str | None = None
    occurred_at: FieldMapping
    bindings: dict[str, BindingMapping]
    execution_inputs: dict[str, FieldMapping] = Field(default_factory=dict)


MappingSpec = ObjectMappingSpec | ActivityMappingSpec


def load_mapping_spec(path: str | Path) -> MappingSpec:
    """Load one approved declarative mapping; no generated code is executed."""

    mapping_path = Path(path)
    try:
        raw = yaml.safe_load(mapping_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"cannot load mapping spec {mapping_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"mapping spec must contain a mapping: {mapping_path}")
    mapping_type = raw.get("mapping_type")
    if mapping_type == "object_snapshot":
        return ObjectMappingSpec.model_validate(raw)
    if mapping_type == "activity_invocation":
        return ActivityMappingSpec.model_validate(raw)
    raise ValueError(f"unsupported mapping_type in {mapping_path}: {mapping_type}")


class MappingCompiler:
    """Finite, deterministic mapping runtime; it never executes generated code."""

    def __init__(self, object_schemas: ObjectSchemaRegistry) -> None:
        self.object_schemas = object_schemas

    def compile_object(
        self,
        row: dict[str, Any],
        spec: ObjectMappingSpec,
        *,
        project_id: str,
    ) -> tuple[StateRecord, datetime]:
        definition = self.object_schemas.definition(spec.target_object_type)
        if tuple(spec.identity) != definition.identity:
            raise ValueError(
                f"mapping identity {spec.identity} does not match object schema "
                f"identity {definition.identity}"
            )
        attributes = {
            target: self._mapped_value(row, mapping) for target, mapping in spec.attributes.items()
        }
        identity = ":".join(str(attributes[name]) for name in spec.identity)
        record = StateRecord(
            record_id=f"{spec.target_object_type}:{identity}",
            record_kind="object",
            record_type=spec.target_object_type,
            project_id=project_id,
            data=attributes,
            state_type="actual",
        )
        self.object_schemas.validate_record(record)
        as_of = self._mapped_value(row, spec.as_of)
        if not isinstance(as_of, datetime):
            raise ValueError("object snapshot as_of mapping must produce datetime")
        return record, as_of

    def compile_activity(
        self,
        row: dict[str, Any],
        spec: ActivityMappingSpec,
        *,
        state: EnterpriseState,
    ) -> ActivityInvocation:
        source_record_id = self._required_source(row, spec.source_record_id)
        occurred_at = self._mapped_value(row, spec.occurred_at)
        if not isinstance(occurred_at, datetime):
            raise ValueError("activity occurred_at mapping must produce datetime")
        bindings = {
            alias: self._resolve_binding(state, row, mapping)
            for alias, mapping in spec.bindings.items()
        }
        execution_inputs = {
            name: self._mapped_value(row, mapping)
            for name, mapping in spec.execution_inputs.items()
        }
        sequence = (
            int(self._required_source(row, spec.source_sequence)) if spec.source_sequence else 0
        )
        return ActivityInvocation(
            invocation_id=f"{spec.mapping_version}:{source_record_id}",
            process_id=spec.process_id,
            activity_id=spec.activity_id,
            occurred_at=occurred_at,
            source_sequence=sequence,
            source_record_id=str(source_record_id),
            bindings=bindings,
            execution_inputs=execution_inputs,
            semantic_status=spec.semantic_status,
            mapping_version=spec.mapping_version,
        )

    @staticmethod
    def _required_source(row: dict[str, Any], source: str | None) -> Any:
        if source is None:
            raise ValueError("source column is required")
        try:
            value = row[source]
        except KeyError as exc:
            raise ValueError(f"source column does not exist: {source}") from exc
        if value is None or value == "":
            raise ValueError(f"source value is empty: {source}")
        return value

    def _mapped_value(self, row: dict[str, Any], mapping: FieldMapping) -> Any:
        value = row.get(mapping.source, mapping.default)
        if value is None or value == "":
            if mapping.default is None:
                raise ValueError(f"source value is empty: {mapping.source}")
            value = mapping.default
        if mapping.transform == "string":
            return str(value)
        if mapping.transform == "decimal":
            decimal_result = Decimal(str(value))
            if not decimal_result.is_finite():
                raise ValueError(f"non-finite decimal: {mapping.source}")
            return decimal_result
        if mapping.transform == "integer":
            return int(value)
        if mapping.transform == "boolean":
            normalized = str(value).strip().lower()
            values = {"true": True, "false": False, "1": True, "0": False}
            if normalized not in values:
                raise ValueError(f"invalid boolean: {mapping.source}")
            return values[normalized]
        datetime_result = (
            value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
        )
        if datetime_result.tzinfo is None or datetime_result.utcoffset() is None:
            raise ValueError(f"datetime requires timezone: {mapping.source}")
        return datetime_result

    @staticmethod
    def _resolve_binding(
        state: EnterpriseState, row: dict[str, Any], mapping: BindingMapping
    ) -> str:
        expected = {
            attribute: MappingCompiler._required_source(row, source)
            for attribute, source in mapping.lookup.items()
        }
        matches = [
            record
            for record in state.objects(mapping.object_type)
            if all(str(record.data.get(key)) == str(value) for key, value in expected.items())
        ]
        if len(matches) != 1:
            raise ValueError(
                f"binding {mapping.object_type} {expected} matched {len(matches)} objects"
            )
        return matches[0].record_id
