from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal, cast

import yaml
from pydantic import Field, ValidationError, model_validator

from core.models import CanonicalModel, ProcessId, StateRecord
from core.processes import ProcessDefinition

AttributeType = Literal["string", "decimal", "integer", "boolean", "datetime", "json"]


class ObjectAttributeDefinition(CanonicalModel):
    type: AttributeType
    required: bool = False
    mutable: bool = True
    default: Any | None = None
    minimum: Decimal | None = None
    allowed_values: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_constraints(self) -> ObjectAttributeDefinition:
        if self.minimum is not None and self.type not in {"decimal", "integer"}:
            raise ValueError("minimum is valid only for numeric attributes")
        if self.allowed_values and self.type != "string":
            raise ValueError("allowed_values is valid only for string attributes")
        return self


class ObjectDefinition(CanonicalModel):
    object_type: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    schema_version: Literal[1] = 1
    identity: tuple[str, ...] = Field(min_length=1)
    attributes: dict[str, ObjectAttributeDefinition]

    @model_validator(mode="after")
    def validate_identity(self) -> ObjectDefinition:
        missing = sorted(set(self.identity) - set(self.attributes))
        if missing:
            raise ValueError(f"identity attributes are not defined: {missing}")
        return self


class ObjectSchemaError(ValueError):
    """Raised when object schemas or their process references are invalid."""


class ObjectSchemaRegistry(CanonicalModel):
    definitions: dict[str, ObjectDefinition]

    def definition(self, object_type: str) -> ObjectDefinition:
        try:
            return self.definitions[object_type]
        except KeyError as exc:
            raise ObjectSchemaError(f"unknown object type: {object_type}") from exc

    def validate_record(self, record: StateRecord) -> None:
        if record.record_kind != "object":
            return
        definition = self.definition(record.record_type)
        unknown = sorted(set(record.data) - set(definition.attributes))
        missing = sorted(
            name
            for name, attribute in definition.attributes.items()
            if attribute.required and name not in record.data and attribute.default is None
        )
        if unknown:
            raise ObjectSchemaError(f"{record.record_id} has undeclared attributes: {unknown}")
        if missing:
            raise ObjectSchemaError(f"{record.record_id} is missing attributes: {missing}")
        for name, value in record.data.items():
            _validate_attribute_value(
                record.record_id,
                name,
                value,
                definition.attributes[name],
            )


def _validate_attribute_value(
    record_id: str,
    name: str,
    value: Any,
    definition: ObjectAttributeDefinition,
) -> None:
    try:
        if definition.type == "string":
            if not isinstance(value, str):
                raise ValueError("must be a string")
            if definition.allowed_values and value not in definition.allowed_values:
                raise ValueError(f"must be one of {sorted(definition.allowed_values)}")
        elif definition.type == "decimal":
            numeric = Decimal(str(value))
            if not numeric.is_finite():
                raise ValueError("must be finite")
            if definition.minimum is not None and numeric < definition.minimum:
                raise ValueError(f"must be at least {definition.minimum}")
        elif definition.type == "integer":
            if isinstance(value, bool) or int(value) != Decimal(str(value)):
                raise ValueError("must be an integer")
            if definition.minimum is not None and Decimal(str(value)) < definition.minimum:
                raise ValueError(f"must be at least {definition.minimum}")
        elif definition.type == "boolean":
            if not isinstance(value, bool):
                raise ValueError("must be a boolean")
        elif definition.type == "datetime":
            parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise ValueError("must include a timezone offset")
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ObjectSchemaError(f"{record_id}.{name} {exc}") from exc


def load_object_schema_registry(directory: str | Path | None = None) -> ObjectSchemaRegistry:
    schema_directory = (
        Path(directory) if directory else Path(__file__).with_name("object_definitions")
    )
    paths = sorted((*schema_directory.glob("*.yaml"), *schema_directory.glob("*.yml")))
    if not paths:
        raise ObjectSchemaError(f"no object schema YAML files found in: {schema_directory}")
    definitions: dict[str, ObjectDefinition] = {}
    for path in paths:
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise ObjectSchemaError(f"cannot load object schema {path}: {exc}") from exc
        if not isinstance(raw, Mapping):
            raise ObjectSchemaError(f"object schema must contain a mapping: {path}")
        try:
            definition = ObjectDefinition.model_validate(cast(dict[str, Any], dict(raw)))
        except ValidationError as exc:
            raise ObjectSchemaError(f"invalid object schema {path}: {exc}") from exc
        if definition.object_type in definitions:
            raise ObjectSchemaError(f"duplicate object type: {definition.object_type}")
        definitions[definition.object_type] = definition
    return ObjectSchemaRegistry(definitions=dict(sorted(definitions.items())))


def validate_process_object_contract(
    processes: Mapping[ProcessId, ProcessDefinition], registry: ObjectSchemaRegistry
) -> None:
    """Require process attribute references to be a subset of declared object attributes."""

    for process in processes.values():
        for activity in process.activities:
            bindings = {binding.alias: binding for binding in activity.inputs}
            for binding in activity.inputs:
                definition = registry.definition(binding.object_type)
                if binding.match_field and binding.match_field not in definition.attributes:
                    raise ObjectSchemaError(
                        f"{process.process_id}.{activity.id} references undeclared attribute "
                        f"{binding.object_type}.{binding.match_field}"
                    )
                if binding.match_field and binding.value_from:
                    source_alias, source_attribute = binding.value_from.split(".", 1)
                    source_binding = bindings[source_alias]
                    source_definition = registry.definition(source_binding.object_type)
                    if source_attribute not in source_definition.attributes:
                        raise ObjectSchemaError(
                            f"{process.process_id}.{activity.id} references undeclared attribute "
                            f"{source_binding.object_type}.{source_attribute}"
                        )
                    if (
                        definition.attributes[binding.match_field].type
                        != source_definition.attributes[source_attribute].type
                    ):
                        raise ObjectSchemaError(
                            f"{process.process_id}.{activity.id} joins incompatible attributes "
                            f"{binding.object_type}.{binding.match_field} and "
                            f"{source_binding.object_type}.{source_attribute}"
                        )
            paths = [
                *(condition.left for condition in activity.enabled_when),
                *(
                    condition.value_from
                    for condition in activity.enabled_when
                    if condition.value_from
                ),
                *(effect.target for effect in activity.operations),
                *(effect.value_from for effect in activity.operations if effect.value_from),
            ]
            if activity.duration.field:
                paths.append(activity.duration.field)
            for path in paths:
                alias, attribute = path.split(".", 1)
                if alias == "execution":
                    continue
                binding = bindings[alias]
                definition = registry.definition(binding.object_type)
                if attribute not in definition.attributes:
                    raise ObjectSchemaError(
                        f"{process.process_id}.{activity.id} references undeclared attribute "
                        f"{binding.object_type}.{attribute}"
                    )
                if path in {effect.target for effect in activity.operations}:
                    declared = definition.attributes[attribute]
                    if not declared.mutable:
                        raise ObjectSchemaError(
                            f"{process.process_id}.{activity.id} modifies immutable attribute "
                            f"{binding.object_type}.{attribute}"
                        )
            for effect in activity.operations:
                alias, attribute = effect.target.split(".", 1)
                target = registry.definition(bindings[alias].object_type).attributes[attribute]
                if effect.operation in {"increase", "decrease"} and target.type not in {
                    "decimal",
                    "integer",
                }:
                    raise ObjectSchemaError(
                        f"{process.process_id}.{activity.id} applies {effect.operation} to "
                        f"non-numeric attribute {bindings[alias].object_type}.{attribute}"
                    )
