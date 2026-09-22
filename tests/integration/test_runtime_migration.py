from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from enterprise_state.database import make_engine, sqlite_url
from enterprise_state.models import AgentRunRow


def test_agent_runs_migration_on_pre_runtime_database(tmp_path: Path) -> None:
    root = Path(__file__).parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    url = sqlite_url(tmp_path / "migration.db")
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "0003_sales_tool_audit")
    engine = make_engine(url)
    try:
        # 0001 uses live Base.metadata, so fresh replay includes today's tables.
        # Remove only this empty new table in the temporary test DB to reproduce
        # the schema of an actual pre-runtime deployment.
        AgentRunRow.__table__.drop(engine, checkfirst=True)
        assert "agent_runs" not in inspect(engine).get_table_names()
        command.upgrade(config, "head")
        assert "agent_runs" in inspect(engine).get_table_names()
        assert "ix_agent_runs_conversation_id" in {
            index["name"] for index in inspect(engine).get_indexes("agent_runs")
        }
    finally:
        engine.dispose()
