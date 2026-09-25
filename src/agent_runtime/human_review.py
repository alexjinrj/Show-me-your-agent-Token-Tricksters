from __future__ import annotations

from typing import Any

REVIEW_TOOLS = {
    "analyze_sales_backlog_intervention",
    "analyze_crm_service_capacity",
    "compare_inventory_replenishment_strategies",
}


def pending_review(run: dict[str, Any]) -> dict[str, Any] | None:
    """A simulation recommendation requires a recorded human decision."""
    if run.get("status") != "completed":
        return None
    evidence = [
        item for item in run.get("evidence", [])
        if item.get("status") == "ok" and item.get("tool_name") in REVIEW_TOOLS
    ]
    if not evidence:
        return None
    return {
        "schema_version": "agent-human-review-v1",
        "status": "pending",
        "source_tool_call_ids": [item["tool_call_id"] for item in evidence],
        "decision": None,
        "reviewer": None,
        "note": None,
        "decided_at": None,
        "execution_status": "not_executed",
    }
