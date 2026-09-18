"""Preview/apply runtime migrations to the same SQLite database used by the API."""

from __future__ import annotations

import argparse
from pathlib import Path

from alembic import command
from alembic.config import Config

from enterprise_state.database import sqlite_url
from interfaces.api.settings import load_settings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="Apply after stopping API and backing up DB"
    )
    args = parser.parse_args()
    db_path = load_settings().db_path.resolve()
    print(f"Target database: {db_path}")
    print("Target revision: head (0006_crm_runtime_evidence)")
    if not args.apply:
        print("Preview only. Stop API, back up this database, then rerun with --apply.")
        return
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    config.set_main_option("sqlalchemy.url", sqlite_url(db_path).replace("%", "%%"))
    command.upgrade(config, "head")
    print("Runtime database migration completed.")


if __name__ == "__main__":
    main()
