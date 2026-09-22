from __future__ import annotations

from typing import Any

from agent_runtime.contracts import RuntimeToolResult
from agent_runtime.registry import RegisteredTool, ToolHandler, ToolRegistry
from tools.crm.tools import CRMAgentTools

CRM_TOOL_DESCRIPTIONS = {
    "get_crm_summary": "Read the CRM service-recovery summary and its data provenance.",
    "list_priority_complaints": "List derived order-service cases, not customer complaints.",
    "get_customer_360": (
        "Read ordered value, derived fulfilment risk and linked order-service cases. "
        "This is not a credit rating."
    ),
    "get_complaint_detail": "Read a derived CASE-SO... service case, order due date and priority.",
    "get_order_timeline": (
        "Trace canonical snapshot order dates/status for a derived service case."
    ),
    "get_inventory_availability": (
        "Read same-snapshot SKU stock net of pending sales obligations, not actual reservations."
    ),
    "estimate_refund_impact": (
        "Read snapshot order amount and standard cost in SGD; refund eligibility is unknown."
    ),
    "compare_resolution_options": (
        "Compare review options for a derived service case; unknown policies remain unavailable."
    ),
    "recommend_resolution": (
        "Investigate a CASE-SO... order-service case and return a snapshot-grounded recommendation."
    ),
    "draft_customer_reply": "Create an unsent reply draft grounded in snapshot order facts.",
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
