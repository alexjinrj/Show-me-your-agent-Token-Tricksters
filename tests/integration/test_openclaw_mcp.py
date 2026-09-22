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
            assert "list_inventory_reorder_candidates" in names
            assert "compare_inventory_replenishment_strategies" in names
            assert "recommend_resolution" in names
            assert "draft_customer_reply" in names
            assert {
                "get_data_catalog",
                "query_snapshot_records",
                "compare_snapshot_periods",
                "query_enterprise_history",
                "analyze_order_spikes",
                "search_public_events",
            } <= names

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
            inventory = await client.call_tool(
                "list_inventory_reorder_candidates",
                {
                    "snapshot_id": snapshot_id,
                    "top_n": 3,
                },
            )
            assert inventory.structured_content is not None
            assert inventory.structured_content["state_type"] == "actual"
            assert len(inventory.structured_content["data"]["candidates"]) <= 3
            crm = await client.call_tool("recommend_resolution", {"complaint_id": "CASE-SO74695"})
            assert crm.structured_content is not None
            assert crm.structured_content["status"] == "ok"
            assert crm.structured_content["reference_id"] == context["crm_dataset_reference"]
            assert crm.structured_content["data"]["result"]["complaintId"] == "CASE-SO74695"
            records = await client.call_tool(
                "query_snapshot_records", {"dataset": "orders", "group_by": ["status"], "limit": 1}
            )
            assert records.structured_content is not None
            assert records.structured_content["data"]["total_matching"] == 500
            history = await client.call_tool("query_enterprise_history", {"as_of": "2026-06-01"})
            assert history.structured_content is not None
            assert history.structured_content["error_code"] == "NOT_IMPLEMENTED"

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
            assert {
                "get_business_context",
                "get_data_catalog",
                "query_snapshot_records",
                "analyze_order_spikes",
                "search_public_events",
            } <= {tool.name for tool in tools.tools}

    asyncio.run(exercise_process())
