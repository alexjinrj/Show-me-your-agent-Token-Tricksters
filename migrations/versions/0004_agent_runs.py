"""Persist runtime conversations, execution events and tool evidence."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_agent_runs"
down_revision = "0003_sales_tool_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "agent_runs" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            "agent_runs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("conversation_id", sa.String(36), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
        )
        op.create_index("ix_agent_runs_conversation_id", "agent_runs", ["conversation_id"])


def downgrade() -> None:
    op.drop_table("agent_runs")
