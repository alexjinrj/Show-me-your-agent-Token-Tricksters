from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal, Protocol
from uuid import uuid4

from sqlalchemy import Engine, select, update
from sqlalchemy.orm import Session

from enterprise_state.models import AgentRunRow, CRMProposalRow


class CRMReadState(Protocol):
    @property
    def reference_id(self) -> str: ...
    @property
    def currency(self) -> str: ...
    def complaint(self, complaint_id: str) -> dict[str, Any]: ...
    def resolution_options(self, complaint_id: str) -> list[dict[str, Any]]: ...
    def provenance(self) -> dict[str, Any]: ...
    def investigate(self, complaint_id: str) -> dict[str, Any]: ...


class CRMProposalStore:
    """Durable human-review records. No customer message, refund or shipment is executed."""

    def __init__(self, engine: Engine, crm: CRMReadState) -> None:
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
            "datasetReference": row.dataset_reference,
            "sourceAgentRunId": row.source_agent_run_id,
            "sourceToolCallId": row.source_tool_call_id,
            "evidence": row.evidence,
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
        source_agent_run_id: str | None = None,
        source_tool_call_id: str | None = None,
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
        if not option["feasible"]:
            raise ValueError("Resolution is not currently feasible under the demo assumptions")
        if bool(source_agent_run_id) != bool(source_tool_call_id):
            raise ValueError("Agent run and tool evidence references must be supplied together")
        source_evidence = None
        if source_agent_run_id:
            with Session(self.engine) as db:
                agent_run = db.get(AgentRunRow, source_agent_run_id)
                if agent_run is None or agent_run.payload["status"] != "completed":
                    raise ValueError("Source AgentRun is missing or incomplete")
                source_evidence = next(
                    (
                        item
                        for item in agent_run.payload["evidence"]
                        if item["tool_call_id"] == source_tool_call_id
                    ),
                    None,
                )
            if (
                source_evidence is None
                or source_evidence["status"] != "ok"
                or source_evidence["tool_name"] != "recommend_resolution"
                or source_evidence.get("reference_id") != self.crm.reference_id
                or source_evidence["data"].get("result", {}).get("complaintId") != complaint["id"]
            ):
                raise ValueError("Source evidence does not match this CRM complaint and dataset")
        now = datetime.now(UTC)
        row = CRMProposalRow(
            id=str(uuid4()),
            complaint_id=complaint["id"],
            customer_id=complaint["customerId"],
            resolution_id=resolution_id,
            resolution_label=option["label"],
            estimated_cost=Decimal(str(option["estimatedCost"])),
            currency=self.crm.currency,
            owner=complaint["ownerRole"],
            status="Pending Review",
            reply_draft=reply_draft,
            internal_draft=internal_draft,
            reviewer=None,
            review_note=None,
            dataset_reference=self.crm.reference_id,
            source_agent_run_id=source_agent_run_id,
            source_tool_call_id=source_tool_call_id,
            evidence={
                "provenance": self.crm.provenance(),
                "investigation": self.crm.investigate(complaint_id),
                "selected_option": option,
                "source_tool_evidence": source_evidence,
            },
            audit=[
                {
                    "at": now.isoformat(),
                    "actor": "Human submitter",
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
            if row.dataset_reference != self.crm.reference_id:
                raise ValueError("CRM proposal is outside the current snapshot scope")
            return self._dump(row)

    def list(self, status: str | None = None) -> list[dict[str, Any]]:
        with Session(self.engine) as db:
            query = select(CRMProposalRow).order_by(
                CRMProposalRow.created_at.desc(), CRMProposalRow.id
            )
            query = query.where(CRMProposalRow.dataset_reference == self.crm.reference_id)
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
            if row.dataset_reference != self.crm.reference_id:
                raise ValueError("Proposal is outside the current snapshot scope")
            now = datetime.now(UTC)
            audit = [
                *row.audit,
                {
                    "at": now.isoformat(),
                    "actor": "Human reviewer",
                    "action": decision,
                    "note": note or f"Marked {decision}",
                },
            ]
            # Atomic compare-and-set: concurrent reviewers cannot overwrite a decision.
            result = db.execute(
                update(CRMProposalRow)
                .where(CRMProposalRow.id == proposal_id, CRMProposalRow.status == "Pending Review")
                .values(
                    status=decision,
                    reviewer=reviewer,
                    review_note=note,
                    updated_at=now,
                    audit=audit,
                )
            )
            if getattr(result, "rowcount", 0) != 1:
                raise ValueError("Proposal was already reviewed; reload its current state")
        return self.get(proposal_id)
