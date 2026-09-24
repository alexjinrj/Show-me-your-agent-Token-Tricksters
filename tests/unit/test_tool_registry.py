from __future__ import annotations

from typing import Any
from uuid import uuid4

from agent_runtime import RegisteredTool, RuntimeToolResult, ToolRegistry
from agent_runtime.sales_registry import (
    EXCEPTION_TOOLS,
    SCENARIO_TOOLS,
    build_sales_tool_registry,
)
from tools.sales import SalesAgentTools


def test_registry_catalog_groups_and_dispatch() -> None:
    calls: list[tuple[dict[str, Any], str]] = []

    def handler(arguments: dict[str, Any], agent_case_id: str) -> RuntimeToolResult:
        calls.append((arguments, agent_case_id))
        return RuntimeToolResult(
            tool_call_id=str(uuid4()),
            tool_name="read_metric",
            status="ok",
            state_type="actual",
            reference_id="snapshot-1",
            data={"value": arguments["value"]},
        )

    registry = ToolRegistry(
        [
            RegisteredTool(
                name="read_metric",
                description="Read one metric.",
                input_schema={
                    "type": "object",
                    "properties": {"value": {"type": "integer"}},
                    "required": ["value"],
                    "additionalProperties": False,
                },
                handler=handler,
                groups=("analysis",),
            )
        ]
    )

    assert registry.names(group="analysis") == ("read_metric",)
    assert registry.catalog()[0]["access"] == "read"
    result = registry.call("read_metric", {"value": 7}, agent_case_id="case-1")
    assert result.data == {"value": 7}
    assert calls == [({"value": 7}, "case-1")]


def test_registry_fails_closed_for_unknown_tools() -> None:
    result = ToolRegistry().call("run_sql", {}, agent_case_id="case-1")
    assert result.status == "error"
    assert result.error_code == "TOOL_NOT_REGISTERED"


def test_sales_registry_groups_and_access_are_consistent(service) -> None:
    registry = build_sales_tool_registry(SalesAgentTools(service.engine))
    assert "trace_process_bottleneck" in EXCEPTION_TOOLS
    assert "trace_process_bottleneck" in SCENARIO_TOOLS
    assert "analyze_sales_backlog_intervention" in SCENARIO_TOOLS
    definitions = {item["name"]: item for item in registry.catalog()}
    assert definitions["trace_process_bottleneck"]["access"] == "read"
    assert definitions["analyze_sales_backlog_intervention"]["access"] == "simulate"
