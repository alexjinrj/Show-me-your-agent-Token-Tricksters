"""Create ingestion, Actual State, and snapshot tables."""

from __future__ import annotations

from alembic import op

from enterprise_state.models import Base

revision = "0001_actual_state"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
