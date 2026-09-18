from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from enterprise_state.database import make_engine, sqlite_url
from enterprise_state.models import CRMProposalRow


def test_crm_migrations_preserve_legacy_review_records(tmp_path: Path) -> None:
    root = Path(__file__).parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    url = sqlite_url(tmp_path / "crm-migration.db")
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "0004_agent_runs")
    engine = make_engine(url)
    try:
        # Fresh 0001 replay uses live metadata. Drop only the empty new CRM table
        # in this temporary database to reproduce an actual pre-CRM deployment.
        CRMProposalRow.__table__.drop(engine, checkfirst=True)
        command.upgrade(config, "0005_crm_proposals")
        assert "evidence" not in {
            column["name"] for column in inspect(engine).get_columns("crm_proposals")
        }
        with engine.begin() as db:
            db.execute(
                text("""
                INSERT INTO crm_proposals
                (id, complaint_id, customer_id, resolution_id, resolution_label, estimated_cost,
                 currency, owner, status, reply_draft, internal_draft,
                 audit, created_at, updated_at)
                VALUES
                ('legacy', 'TKT-004', 'CUS-001', 'refund', 'Full refund', 12.50,
                 'BRL', 'Reviewer', 'Pending Review', '', '', '[]',
                 '2026-09-17 12:00:00', '2026-09-17 12:00:00')
            """)
            )
        command.upgrade(config, "head")
        columns = {column["name"] for column in inspect(engine).get_columns("crm_proposals")}
        assert {
            "dataset_reference",
            "source_agent_run_id",
            "source_tool_call_id",
            "evidence",
        } <= columns
        assert "ix_crm_proposals_status" in {
            index["name"] for index in inspect(engine).get_indexes("crm_proposals")
        }
        with engine.connect() as db:
            legacy = db.execute(
                text("SELECT status, evidence FROM crm_proposals WHERE id='legacy'")
            ).one()
            assert legacy == ("Pending Review", None)
        command.downgrade(config, "0005_crm_proposals")
        assert "evidence" not in {
            column["name"] for column in inspect(engine).get_columns("crm_proposals")
        }
        command.upgrade(config, "head")
    finally:
        engine.dispose()


def test_migration_cli_previews_without_writing_and_applies_configured_database(
    tmp_path: Path,
) -> None:
    root = Path(__file__).parents[2]
    database = tmp_path / "new-directory" / "configured.db"
    env = {**os.environ, "BC_DB_PATH": str(database)}
    argv = [sys.executable, str(root / "scripts/migrate_runtime.py")]
    preview = subprocess.run(
        argv, cwd=root, env=env, capture_output=True, text=True, timeout=30, check=True
    )
    assert str(database) in preview.stdout
    assert "Preview only" in preview.stdout
    assert not database.parent.exists()
    for _ in range(2):
        subprocess.run(
            [*argv, "--apply"],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
    engine = make_engine(sqlite_url(database))
    try:
        with engine.connect() as db:
            assert db.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
                "0006_crm_runtime_evidence"
            )
        assert "evidence" in {
            column["name"] for column in inspect(engine).get_columns("crm_proposals")
        }
    finally:
        engine.dispose()
