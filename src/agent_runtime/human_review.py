from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import Engine, update
from sqlalchemy.orm import Session

from enterprise_state.models import AgentRunRow

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


class HumanReviewService:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def decide(
        self,
        run_id: str,
        decision: Literal["approved", "rejected"],
        reviewer: str,
        note: str,
    ) -> dict[str, Any]:
        if not reviewer.strip():
            raise ValueError("Reviewer is required")
        with Session(self.engine) as db, db.begin():
            row = db.get(AgentRunRow, run_id)
            if row is None:
                raise LookupError("Agent run not found")
            payload = dict(row.payload)
            review = payload.get("human_review")
            if not isinstance(review, dict):
                raise ValueError("This run has no reviewable simulated recommendation")
            if review.get("status") != "pending":
                raise ValueError("Review decision has already been recorded")
            review = {
                **review,
                "status": "decided",
                "decision": decision,
                "reviewer": reviewer.strip(),
                "note": note.strip(),
                "decided_at": datetime.now(UTC).isoformat(),
            }
            payload["human_review"] = review
            changed = db.connection().execute(
                update(AgentRunRow)
                .where(
                    AgentRunRow.id == run_id,
                    AgentRunRow.payload["human_review"]["status"].as_string() == "pending",
                )
                .values(payload=payload)
            )
            if changed.rowcount != 1:
                raise ValueError("Review decision has already been recorded")
            return review
