from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from business_coordinator.config.loader import (
    hash_process_catalog,
    load_process_definitions,
)
from business_coordinator.domain.models import ProcessId, ResourceType
from business_coordinator.domain.processes import ProcessDefinition, ProcessNodeDefinition


@dataclass(frozen=True)
class RuntimeProcessCatalog:
    """Validated, read-only process structure consumed by the simulation engine."""

    definitions: Mapping[ProcessId, ProcessDefinition]
    version_label: str
    content_hash: str

    def definition(self, process_id: ProcessId) -> ProcessDefinition:
        return self.definitions[process_id]

    def node(self, process_id: ProcessId, node_id: str) -> ProcessNodeDefinition:
        return self.definition(process_id).node(node_id)

    def resource(self, process_id: ProcessId, node_id: str) -> ResourceType:
        return self.node(process_id, node_id).resource

    def processing_hours(self, process_id: ProcessId, node_id: str) -> Decimal:
        return self.node(process_id, node_id).processing_time_hours

    def parameter(self, process_id: ProcessId, name: str) -> Decimal:
        try:
            return self.definition(process_id).parameters[name]
        except KeyError as exc:
            raise ValueError(f"missing process parameter: {process_id}.{name}") from exc

    def next_node(self, process_id: ProcessId, node_id: str) -> str | None:
        transitions = self.node(process_id, node_id).next
        if not transitions:
            return None
        if len(transitions) != 1:
            raise ValueError(f"simulation MVP requires one transition from {process_id}.{node_id}")
        return transitions[0].target

    def path_from(self, process_id: ProcessId, start_node_id: str) -> tuple[str, ...]:
        path: list[str] = []
        current: str | None = start_node_id
        while current is not None:
            if current in path:
                raise ValueError(f"cycle detected in {process_id}: {current}")
            path.append(current)
            current = self.next_node(process_id, current)
        return tuple(path)

    def resource_for_node(self, node_id: str) -> ResourceType:
        matches = [
            node.resource
            for definition in self.definitions.values()
            for node in definition.nodes
            if node.id == node_id
        ]
        if len(matches) != 1:
            raise ValueError(f"node ID must identify one configured resource: {node_id}")
        return matches[0]


def load_runtime_process_catalog(
    config_dir: Path | None = None,
) -> RuntimeProcessCatalog:
    root = config_dir or Path(__file__).parents[3] / "config" / "processes"
    definitions = load_process_definitions(root)
    versions = ",".join(
        f"{process_id}:v{definition.version}" for process_id, definition in definitions.items()
    )
    return RuntimeProcessCatalog(
        definitions=definitions,
        version_label=versions,
        content_hash=hash_process_catalog(definitions),
    )
