#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from enterprise_state.database import create_schema, make_engine, sqlite_url
from enterprise_state.service import ActualStateService, commit_demo_files

ORDER = (
    "customers",
    "suppliers",
    "items",
    "inventory",
    "sales_orders",
    "purchase_orders",
    "resources",
    "opening_balances",
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="actual_state.db")
    parser.add_argument("--data", default="data/load_data/adventureworks_demo")
    arguments = parser.parse_args()
    engine = make_engine(sqlite_url(arguments.database))
    create_schema(engine)
    service = ActualStateService(engine, source_system="microsoft-adventureworks-demo")
    root = Path(arguments.data)
    commit_demo_files(service, ((name, root / f"{name}.csv") for name in ORDER))
    manifest = service.create_snapshot(datetime.fromisoformat("2026-09-12T23:59:00+08:00"))
    print({"counts": service.counts(), "snapshot": manifest.model_dump(mode="json")})


if __name__ == "__main__":
    main()
