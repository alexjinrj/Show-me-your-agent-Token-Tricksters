from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine, event

from business_coordinator.persistence.models import Base


def make_engine(url: str = "sqlite+pysqlite:///:memory:") -> Engine:
    engine = create_engine(url, future=True)
    if engine.dialect.name == "sqlite":
        event.listen(
            engine,
            "connect",
            lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"),
        )
    return engine


def sqlite_url(path: str | Path) -> str:
    return f"sqlite+pysqlite:///{Path(path).resolve()}"


def create_schema(engine: Engine) -> None:
    Base.metadata.create_all(engine)
