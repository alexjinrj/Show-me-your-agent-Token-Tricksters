from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from mcp import Client
from mcp.client.stdio import StdioServerParameters

from interfaces.mcp.server import mcp


def test_openclaw_mcp_discovers_context_and_audited_sales_tools() -> None:
    async def exercise_server() -> None:
        async with Client(mcp) as client:
            tools = await client.list_tools()
            names = {tool.name for tool in tools.tools}
            assert "get_business_context" in names
            assert "get_actual_state_summary" in names
            assert "run_simulation" in names
            assert "compare_simulation_runs" in names

            context_result = await client.call_tool("get_business_context", {})
            context = context_result.structured_content
            assert context is not None
            snapshot_id = context["base_snapshot_id"]

            summary_result = await client.call_tool(
                "get_actual_state_summary",
                {"snapshot_id": snapshot_id},
            )
            summary = summary_result.structured_content
            assert summary is not None
            assert summary["status"] == "ok"
            assert summary["state_type"] == "actual"
            assert summary["data"]["sales_order_count"] == 500
            assert summary["tool_call_id"]

    asyncio.run(exercise_server())


def test_openclaw_can_launch_the_server_over_stdio() -> None:
    async def exercise_process() -> None:
        project_root = Path(__file__).parents[2]
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "interfaces.mcp.server"],
            cwd=str(project_root),
        )
        async with Client(parameters) as client:
            tools = await client.list_tools()
            assert any(tool.name == "get_business_context" for tool in tools.tools)

    asyncio.run(exercise_process())
