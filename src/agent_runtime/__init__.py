"""Shared Agent runtime with registered business tools."""

from agent_runtime.contracts import (
    RuntimeToolResult,
)
from agent_runtime.inventory_registry import (
    register_inventory_tools,
)
from agent_runtime.registry import (
    RegisteredTool,
    ToolRegistry,
)
from agent_runtime.sales_registry import (
    build_sales_tool_registry,
)

__all__ = [
    "RegisteredTool",
    "RuntimeToolResult",
    "ToolRegistry",
    "build_sales_tool_registry",
    "register_inventory_tools",
]