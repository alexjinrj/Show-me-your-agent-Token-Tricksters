from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from enterprise_state.models import CRMProposalRow
from tools.crm.service import CRMService


class CRMProposalStore:
    """Durable human-review records. No customer message, refund or shipment is executed."""

    def __init__(self, engine: Engine, crm: CRMService) -> None:
        self.engine = engine
        self.crm = crm

    @staticmethod
    def _dump(row: CRMProposalRow) -> dict[str, Any]:
        return {
            "id": row.id,
            "complaintId": row.complaint_id,
            "customerId": row.customer_id,
            "resolutionId": row.resolution_id,
            "resolutionLabel": row.resolution_label,
            "estimatedCost": str(row.estimated_cost),
            "currency": row.currency,
            "owner": row.owner,
            "status": row.status,
            "replyDraft": row.reply_draft,
            "internalDraft": row.internal_draft,
            "reviewer": row.reviewer,
            "reviewNote": row.review_note,
            "audit": list(row.audit),
            "createdAt": row.created_at.isoformat(),
            "updatedAt": row.updated_at.isoformat(),
            "effect": (
                "Review state only. No customer contact, refund, shipment or "
                "Actual State write was executed."
            ),
        }

    def create(
        self,
        complaint_id: str,
        resolution_id: str,
        reply_draft: str = "",
        internal_draft: str = "",
    ) -> dict[str, Any]:
        complaint = self.crm.complaint(complaint_id)
        option = next(
            (
                row
                for row in self.crm.resolution_options(complaint_id)
                if row["id"] == resolution_id
            ),
            None,
        )
        if option is None:
            raise ValueError(f"Resolution {resolution_id} is not available")
        now = datetime.now(UTC)
        row = CRMProposalRow(
            id=str(uuid4()),
            complaint_id=complaint["id"],
            customer_id=complaint["customerId"],
            resolution_id=resolution_id,
            resolution_label=option["label"],
            estimated_cost=Decimal(str(option["estimatedCost"])),
            currency="BRL",
            owner=complaint["ownerRole"],
            status="Pending Review",
            reply_draft=reply_draft,
            internal_draft=internal_draft,
            reviewer=None,
            review_note=None,
            audit=[
                {
                    "at": now.isoformat(),
                    "actor": "CRM Agent",
                    "action": "Created proposal",
                    "note": "Submitted for human review; no business action executed.",
                }
            ],
            created_at=now,
            updated_at=now,
        )
        proposal_id = row.id
        with Session(self.engine) as db, db.begin():
            db.add(row)
        return self.get(proposal_id)

    def get(self, proposal_id: str) -> dict[str, Any]:
        with Session(self.engine) as db:
            row = db.get(CRMProposalRow, proposal_id)
            if row is None:
                raise ValueError("CRM proposal was not found")
            return self._dump(row)

    def list(self, status: str | None = None) -> list[dict[str, Any]]:
        with Session(self.engine) as db:
            query = select(CRMProposalRow).order_by(
                CRMProposalRow.created_at.desc(), CRMProposalRow.id
            )
            if status:
                query = query.where(CRMProposalRow.status == status)
            return [self._dump(row) for row in db.scalars(query).all()]

    def decide(
        self,
        proposal_id: str,
        decision: Literal["Approved", "Rejected"],
        reviewer: str,
        note: str = "",
    ) -> dict[str, Any]:
        with Session(self.engine) as db, db.begin():
            row = db.get(CRMProposalRow, proposal_id)
            if row is None:
                raise ValueError("CRM proposal was not found")
            if row.status != "Pending Review":
                raise ValueError(f"Proposal is already {row.status}")
            now = datetime.now(UTC)
            row.status = decision
            row.reviewer = reviewer
            row.review_note = note
            row.updated_at = now
            row.audit = [
                *row.audit,
                {
                    "at": now.isoformat(),
                    "actor": "Human reviewer",
                    "action": decision,
                    "note": note or f"Marked {decision}",
                },
            ]
        return self.get(proposal_id)
