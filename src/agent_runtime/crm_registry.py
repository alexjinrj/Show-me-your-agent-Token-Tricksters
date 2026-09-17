from __future__ import annotations

from typing import Any

from agent_runtime.contracts import RuntimeToolResult
from agent_runtime.registry import RegisteredTool, ToolHandler, ToolRegistry
from tools.crm.tools import CRMAgentTools

CRM_TOOL_DESCRIPTIONS = {
    "get_crm_summary": "Read the CRM service-recovery summary and its data provenance.",
    "list_priority_complaints": "List open complaints ordered by deterministic service priority.",
    "get_customer_360": (
        "Read customer value, relationship risk and linked complaint evidence. "
        "This is not a credit rating."
    ),
    "get_complaint_detail": "Read one complaint's SLA, priority evidence, owner and next action.",
    "get_order_timeline": (
        "Trace Olist order dates and labelled CRM replay events for one complaint."
    ),
    "get_inventory_availability": (
        "Read labelled demo replacement-stock assumptions for one complaint."
    ),
    "estimate_refund_impact": (
        "Estimate labelled demo refund, replacement and service-credit exposure."
    ),
    "compare_resolution_options": (
        "Compare refund, replacement, credit and monitor options without executing any action."
    ),
    "recommend_resolution": (
        "Investigate one complaint and return a grounded service-recovery recommendation."
    ),
    "draft_customer_reply": "Create an unsent reply draft grounded in the complaint evidence.",
}


def register_crm_tools(registry: ToolRegistry, tools: CRMAgentTools) -> None:
    def handler(name: str) -> ToolHandler:
        def call(arguments: dict[str, Any], agent_case_id: str) -> RuntimeToolResult:
            return tools.call(name, arguments, agent_case_id=agent_case_id)

        return call

    for name, schema in tools.schemas().items():
        registry.register(
            RegisteredTool(
                name=name,
                description=CRM_TOOL_DESCRIPTIONS[name],
                input_schema=schema,
                handler=handler(name),
                access="read",
                groups=("crm", "service-recovery"),
            )
        )
