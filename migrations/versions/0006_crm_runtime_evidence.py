"""Link CRM human-review records to immutable runtime evidence."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_crm_runtime_evidence"
down_revision = "0005_crm_proposals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("crm_proposals")}
    for name, kind in (
        ("dataset_reference", sa.String(80)),
        ("source_agent_run_id", sa.String(36)),
        ("source_tool_call_id", sa.String(36)),
        ("evidence", sa.JSON()),
    ):
        if name not in columns:
            op.add_column("crm_proposals", sa.Column(name, kind, nullable=True))
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("crm_proposals")}
    if "ix_crm_proposals_status" not in indexes:
        op.create_index("ix_crm_proposals_status", "crm_proposals", ["status"])


def downgrade() -> None:
    op.drop_index("ix_crm_proposals_status", table_name="crm_proposals")
    with op.batch_alter_table("crm_proposals") as batch:
        for name in ("evidence", "source_tool_call_id", "source_agent_run_id", "dataset_reference"):
            batch.drop_column(name)
