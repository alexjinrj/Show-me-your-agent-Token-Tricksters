"""Add persistent simulation sessions, runs, results, and accounting impacts."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_simulation"
down_revision = "0001_actual_state"
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {str(column["name"]) for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "simulation_sessions" in tables:
        existing = _columns("simulation_sessions")
        with op.batch_alter_table("simulation_sessions") as batch:
            if "description" not in existing:
                batch.add_column(
                    sa.Column("description", sa.String(1000), nullable=False, server_default="")
                )
            if "parent_session_id" not in existing:
                batch.add_column(sa.Column("parent_session_id", sa.String(36), nullable=True))
                batch.create_foreign_key(
                    "fk_simulation_session_parent",
                    "simulation_sessions",
                    ["parent_session_id"],
                    ["id"],
                )
            if "created_at" not in existing:
                batch.add_column(
                    sa.Column(
                        "created_at",
                        sa.DateTime(timezone=True),
                        nullable=False,
                        server_default=sa.func.current_timestamp(),
                    )
                )
            if "state_type" not in existing:
                batch.add_column(
                    sa.Column(
                        "state_type", sa.String(10), nullable=False, server_default="simulated"
                    )
                )
    if "simulation_events" in tables:
        existing = _columns("simulation_events")
        with op.batch_alter_table("simulation_events") as batch:
            if "effective_day" not in existing:
                batch.add_column(
                    sa.Column(
                        "effective_day",
                        sa.Numeric(12, 4),
                        nullable=False,
                        server_default="0",
                    )
                )
            if "created_at" not in existing:
                batch.add_column(
                    sa.Column(
                        "created_at",
                        sa.DateTime(timezone=True),
                        nullable=False,
                        server_default=sa.func.current_timestamp(),
                    )
                )
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "simulation_runs" not in tables:
        op.create_table(
            "simulation_runs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "simulation_session_id",
                sa.String(36),
                sa.ForeignKey("simulation_sessions.id"),
                nullable=False,
            ),
            sa.Column("snapshot_hash", sa.String(64), nullable=False),
            sa.Column("process_definition_version", sa.String(255), nullable=False),
            sa.Column("process_definition_hash", sa.String(64), nullable=False),
            sa.Column("scenario_event_hash", sa.String(64), nullable=False),
            sa.Column("horizon_days", sa.Integer(), nullable=False),
            sa.Column("random_seed", sa.Integer(), nullable=False),
            sa.Column("result_hash", sa.String(64), nullable=False),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    if "simulation_results" not in tables:
        op.create_table(
            "simulation_results",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "simulation_run_id",
                sa.String(36),
                sa.ForeignKey("simulation_runs.id"),
                nullable=False,
                unique=True,
            ),
            sa.Column("summary_metrics", sa.JSON(), nullable=False),
            sa.Column("event_trace", sa.JSON(), nullable=False),
        )
    if "accounting_impacts" not in tables:
        op.create_table(
            "accounting_impacts",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "simulation_run_id",
                sa.String(36),
                sa.ForeignKey("simulation_runs.id"),
                nullable=False,
            ),
            sa.Column("event_type", sa.String(80), nullable=False),
            sa.Column("object_id", sa.String(36), nullable=False),
            sa.Column("simulated_hour", sa.Numeric(14, 4), nullable=False),
            sa.Column("lines", sa.JSON(), nullable=False),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    for table_name in ("accounting_impacts", "simulation_results", "simulation_runs"):
        if table_name in tables:
            op.drop_table(table_name)
    if "simulation_events" in tables:
        existing = _columns("simulation_events")
        with op.batch_alter_table("simulation_events") as batch:
            for column in ("created_at", "effective_day"):
                if column in existing:
                    batch.drop_column(column)
    if "simulation_sessions" in tables:
        existing = _columns("simulation_sessions")
        with op.batch_alter_table("simulation_sessions") as batch:
            if "parent_session_id" in existing:
                batch.drop_constraint("fk_simulation_session_parent", type_="foreignkey")
            for column in ("state_type", "created_at", "parent_session_id", "description"):
                if column in existing:
                    batch.drop_column(column)
