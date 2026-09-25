from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import Engine, update
from sqlalchemy.orm import Session

from enterprise_state.models import AgentRunRow


class HumanReviewService:
    """Persist one review decision without executing the proposed action."""

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
