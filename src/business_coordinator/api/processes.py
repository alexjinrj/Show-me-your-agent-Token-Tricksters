from __future__ import annotations

from typing import Any

from business_coordinator.domain.processes import ProcessDefinition
from business_coordinator.simulation.process_runtime import RuntimeProcessCatalog


def process_graph(definition: ProcessDefinition) -> dict[str, Any]:
    """Serialize one already-validated process definition for the UI."""
    nodes = [node.model_dump(mode="python") for node in definition.nodes]
    edges = [
        {
            "source": node.id,
            "target": transition.target,
            "guard": transition.guard,
        }
        for node in definition.nodes
        for transition in node.next
    ]
    return {
        "process_id": definition.process_id,
        "version": definition.version,
        "label": definition.label,
        "initial_node_id": definition.initial_node_id,
        "terminal_node_ids": definition.terminal_node_ids,
        "nodes": nodes,
        "edges": edges,
        "resources": sorted({node.resource for node in definition.nodes}),
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
