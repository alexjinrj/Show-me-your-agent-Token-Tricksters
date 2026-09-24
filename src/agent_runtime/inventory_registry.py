from __future__ import annotations

from typing import Any

from agent_runtime.registry import (
    RegisteredTool,
    ToolAccess,
    ToolRegistry,
)
from tools.inventory.contracts import INVENTORY_TOOL_INPUTS
from tools.inventory.tools import InventoryAgentTools

TOOL_DESCRIPTIONS = {
    "list_inventory_reorder_candidates": (
        "List actual snapshot inventory reorder candidates."
    ),
    "compare_inventory_replenishment_strategies": (
        "Compare four persisted inventory strategies "
        "with matching seed and horizon."
    ),
}

SIMULATION_TOOLS = frozenset(
    {
        "compare_inventory_replenishment_strategies",
    }
)


def register_inventory_tools(
    registry: ToolRegistry,
    inventory_tools: InventoryAgentTools,
) -> None:
    """Register Inventory tools in the shared runtime catalog."""

    def handler(name: str) -> Any:
        return lambda arguments, agent_case_id: inventory_tools.call(
            name,
            arguments,
            agent_case_id=agent_case_id,
        )

    for name, input_model in INVENTORY_TOOL_INPUTS.items():
        access: ToolAccess = (
            "simulate"
            if name in SIMULATION_TOOLS
            else "read"
        )

        registry.register(
            RegisteredTool(
                name=name,
                description=TOOL_DESCRIPTIONS[name],
                input_schema=input_model.model_json_schema(),
                handler=handler(name),
                access=access,
                groups=("inventory",),
            )
        )