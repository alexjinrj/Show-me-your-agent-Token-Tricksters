"""Composition root: SQL/tools dependencies stay outside agent_runtime."""

from __future__ import annotations

import os
from typing import Any, Literal
from uuid import uuid4

from agent_runtime.contracts import RuntimeToolResult
from agent_runtime.crm_registry import register_crm_tools
from agent_runtime.executor import ToolExecutor
from agent_runtime.openclaw import OpenClawGateway
from agent_runtime.registry import RegisteredTool, ToolHandler
from agent_runtime.sales_registry import build_sales_tool_registry
from agent_runtime.service import RuntimeService
from enterprise_state.runtime_store import SQLRuntimeStore
from interfaces.api.context import DemoContext
from tools.crm.tools import CRMAgentTools
from tools.inventory.tools import InventoryAgentTools
from tools.sales.tools import SalesAgentTools


def build_runtime(context: DemoContext, *, use_gateway: bool = True) -> RuntimeService:
    registry = build_sales_tool_registry(SalesAgentTools(context.engine))
    register_crm_tools(registry, CRMAgentTools(context.crm))
    inventory = InventoryAgentTools(context.engine)

    def inventory_handler(name: str) -> ToolHandler:
        def call(arguments: dict[str, Any], agent_case_id: str) -> RuntimeToolResult:
            data = inventory.call(name, arguments)
            state: Literal["actual", "simulated"] = (
                "simulated" if name == "compare_inventory_replenishment_strategies" else "actual"
            )
            return RuntimeToolResult(
                tool_call_id=str(uuid4()),
                tool_name=name,
                status="ok",
                state_type=state,
                reference_id=data["snapshot_id"],
                data=data,
            )

        return call

    for name, schema in inventory.schemas().items():
        registry.register(
            RegisteredTool(
                name=name,
                description=(
                    "Compare four persisted inventory strategies with matching seed/horizon."
                    if name.startswith("compare")
                    else "List actual snapshot inventory reorder candidates."
                ),
                input_schema=schema,
                handler=inventory_handler(name),
                access="simulate" if name.startswith("compare") else "read",
                groups=("inventory",),
            )
        )
    store = SQLRuntimeStore(context.engine)
    url, token = os.getenv("BC_OPENCLAW_URL", ""), os.getenv("BC_OPENCLAW_TOKEN", "")
    gateway = (
        OpenClawGateway(
            url,
            token,
            os.getenv("BC_OPENCLAW_AGENT_ID", "business-coordinator"),
        )
        if use_gateway and url and token
        else None
    )
    return RuntimeService(
        ToolExecutor(registry, store.check_scope, store.audit),
        store,
        context.base_snapshot_id,
        gateway,
    )
