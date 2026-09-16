from __future__ import annotations

from typing import Any

from agent_runtime.registry import RegisteredTool, ToolAccess, ToolRegistry
from tools.sales.contracts import TOOL_INPUTS
from tools.sales.tools import SalesAgentTools

TOOL_DESCRIPTIONS = {
    "get_actual_state_summary": "Read current sales orders, backlog, and snapshot lineage.",
    "list_exceptions": "List current sales backlog and inventory exceptions.",
    "trace_process_bottleneck": "Inspect current Order-to-Cash queues and capacity evidence.",
    "trace_business_object": "Trace a sales order by its order number.",
    "get_metric_history": "Check whether an actual historical metric is available.",
    "create_simulation_session": "Create an isolated scenario session from an actual snapshot.",
    "get_simulation_state": "Inspect an isolated simulation session and its events.",
    "fork_simulation_session": "Fork a baseline simulation session for an alternative.",
    "add_simulation_event": "Add a permitted warehouse or supplier scenario event.",
    "run_simulation": "Run an isolated scenario with an explicit horizon and seed.",
    "compare_simulation_runs": "Compare compatible baseline and alternative runs.",
}

EXCEPTION_TOOLS = (
    "get_actual_state_summary",
    "list_exceptions",
    "trace_business_object",
    "get_metric_history",
)
SCENARIO_TOOLS = (
    "get_actual_state_summary",
    "list_exceptions",
    "create_simulation_session",
    "get_simulation_state",
    "fork_simulation_session",
    "add_simulation_event",
    "run_simulation",
    "compare_simulation_runs",
)


def build_sales_tool_registry(sales_tools: SalesAgentTools) -> ToolRegistry:
    """Adapt the audited sales surface to the shared runtime registry."""

    def handler(name: str) -> Any:
        return lambda arguments, agent_case_id: sales_tools.call(
            name,
            arguments,
            agent_case_id=agent_case_id,
        )

    tools = []
    for name, input_model in TOOL_INPUTS.items():
        access: ToolAccess = "simulate" if name in SCENARIO_TOOLS[2:] else "read"
        groups = tuple(
            group
            for group, names in (("exceptions", EXCEPTION_TOOLS), ("scenario", SCENARIO_TOOLS))
            if name in names
        )
        tools.append(
            RegisteredTool(
                name=name,
                description=TOOL_DESCRIPTIONS[name],
                input_schema=input_model.model_json_schema(),
                handler=handler(name),
                access=access,
                groups=groups,
            )
        )
    return ToolRegistry(tools)
