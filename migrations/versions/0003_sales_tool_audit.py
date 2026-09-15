"""Add an audit trail for bounded sales-agent tool calls."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_sales_tool_audit"
down_revision = "0002_simulation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "tool_call_audit" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            "tool_call_audit",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("agent_case_id", sa.String(80), nullable=False),
            sa.Column("tool_name", sa.String(80), nullable=False),
            sa.Column("argument_hash", sa.String(64), nullable=False),
            sa.Column("result_reference", sa.String(80), nullable=True),
            sa.Column("result_hash", sa.String(64), nullable=True),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("error_code", sa.String(80), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )


def downgrade() -> None:
    op.drop_table("tool_call_audit")
