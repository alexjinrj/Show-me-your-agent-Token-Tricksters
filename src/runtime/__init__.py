"""Shared Agent runtime with registered business tools."""

from runtime.contracts import (
    RuntimeToolResult,
)
from runtime.inventory_registry import (
    register_inventory_tools,
)
from runtime.registry import (
    RegisteredTool,
    ToolRegistry,
)
from runtime.sales_registry import (
    build_sales_tool_registry,
)

__all__ = [
    "RegisteredTool",
    "RuntimeToolResult",
    "ToolRegistry",
    "build_sales_tool_registry",
    "register_inventory_tools",
]