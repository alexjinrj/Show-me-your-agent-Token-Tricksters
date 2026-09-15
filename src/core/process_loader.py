from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import yaml
from pydantic import ValidationError

from core.models import ProcessId
from core.processes import ProcessDefinition
from core.serialization import canonical_hash

SUPPORTED_PROCESS_VERSIONS: dict[ProcessId, frozenset[int]] = {
    "order_to_cash": frozenset({2}),
    "procure_to_pay": frozenset({2}),
}


class ProcessConfigurationError(ValueError):
    """Raised when a process file cannot be parsed or violates its contract."""


def load_process_definition(path: str | Path) -> ProcessDefinition:
    """Load and fully validate one versioned process definition."""

    process_path = Path(path)
    if process_path.suffix.lower() not in {".yaml", ".yml"}:
        raise ProcessConfigurationError(f"process file must be YAML: {process_path}")
    try:
        raw = yaml.safe_load(process_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ProcessConfigurationError(f"cannot read process file {process_path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ProcessConfigurationError(f"invalid YAML in {process_path}: {exc}") from exc
    if not isinstance(raw, Mapping):
        raise ProcessConfigurationError(f"process file must contain a mapping: {process_path}")
    try:
        definition = ProcessDefinition.model_validate(cast(dict[str, Any], dict(raw)))
    except ValidationError as exc:
        raise ProcessConfigurationError(
            f"invalid process definition {process_path}: {exc}"
        ) from exc

    supported_versions = SUPPORTED_PROCESS_VERSIONS[definition.process_id]
    if definition.version not in supported_versions:
        supported = ", ".join(str(version) for version in sorted(supported_versions))
        raise ProcessConfigurationError(
            f"unsupported version {definition.version} for {definition.process_id}; "
            f"supported: {supported}"
        )
    if process_path.stem != definition.process_id:
        raise ProcessConfigurationError(
            f"file name {process_path.stem!r} must match process_id {definition.process_id!r}"
        )
    return definition


def load_process_definitions(directory: str | Path) -> dict[ProcessId, ProcessDefinition]:
    """Load a directory as a deterministic process-ID keyed catalog."""

    process_directory = Path(directory)
    if not process_directory.is_dir():
        raise ProcessConfigurationError(f"process configuration directory not found: {directory}")
    paths = sorted((*process_directory.glob("*.yaml"), *process_directory.glob("*.yml")))
    if not paths:
        raise ProcessConfigurationError(f"no process YAML files found in: {directory}")

    definitions: dict[ProcessId, ProcessDefinition] = {}
    for path in paths:
        definition = load_process_definition(path)
        if definition.process_id in definitions:
            raise ProcessConfigurationError(f"duplicate process_id: {definition.process_id}")
        definitions[definition.process_id] = definition
    return dict(sorted(definitions.items()))


def hash_process_definition(definition: ProcessDefinition) -> str:
    """Hash semantic configuration, independent of YAML layout and comments."""

    return canonical_hash(definition)


def hash_process_catalog(definitions: Mapping[ProcessId, ProcessDefinition]) -> str:
    """Hash a process catalog using stable process-ID ordering."""

    return canonical_hash(
        {process_id: definitions[process_id] for process_id in sorted(definitions)}
    )
