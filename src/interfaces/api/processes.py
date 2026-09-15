from __future__ import annotations

from typing import Any

from core.processes import ProcessDefinition
from core.simulation.process_runtime import RuntimeProcessCatalog


def process_graph(definition: ProcessDefinition) -> dict[str, Any]:
    """Serialize one already-validated process definition for the UI."""
    activities = [activity.model_dump(mode="python") for activity in definition.activities]
    edges = [
        {
            "source": activity.id,
            "target": transition.target,
            "conditions": [
                condition.model_dump(mode="python") for condition in transition.conditions
            ],
        }
        for activity in definition.activities
        for transition in activity.next
    ]
    return {
        "process_id": definition.process_id,
        "version": definition.version,
        "label": definition.label,
        "schema_version": definition.schema_version,
        "initial_node_id": definition.initial_node_id,
        "terminal_node_ids": definition.terminal_node_ids,
        "primary_object_type": definition.primary_object_type,
        "active_statuses": definition.active_statuses,
        "activities": activities,
        "nodes": activities,
        "edges": edges,
        "resources": sorted(
            {activity.resource for activity in definition.activities if activity.resource}
        ),
        "parameters": definition.parameters,
    }


def load_all_processes(catalog: RuntimeProcessCatalog) -> dict[str, Any]:
    """Expose the same validated catalog consumed by the simulation engine."""
    return {
        "version_label": catalog.version_label,
        "content_hash": catalog.content_hash,
        "processes": [
            process_graph(catalog.definitions[process_id])
            for process_id in sorted(catalog.definitions)
        ],
    }
