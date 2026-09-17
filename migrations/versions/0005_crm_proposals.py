"""Persist CRM service-recovery proposals and human review decisions."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_crm_proposals"
down_revision = "0004_agent_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "crm_proposals" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "crm_proposals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("complaint_id", sa.String(20), nullable=False),
        sa.Column("customer_id", sa.String(20), nullable=False),
        sa.Column("resolution_id", sa.String(20), nullable=False),
        sa.Column("resolution_label", sa.String(120), nullable=False),
        sa.Column("estimated_cost", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("owner", sa.String(120), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("reply_draft", sa.String(4000), nullable=False),
        sa.Column("internal_draft", sa.String(4000), nullable=False),
        sa.Column("reviewer", sa.String(120), nullable=True),
        sa.Column("review_note", sa.String(1000), nullable=True),
        sa.Column("audit", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_crm_proposals_complaint_id", "crm_proposals", ["complaint_id"])
    op.create_index("ix_crm_proposals_customer_id", "crm_proposals", ["customer_id"])
    op.create_index("ix_crm_proposals_status", "crm_proposals", ["status"])


def downgrade() -> None:
    op.drop_table("crm_proposals")
