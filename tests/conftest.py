from pathlib import Path

import pytest

from infra.database import create_schema, make_engine
from infra.service import ActualStateService


@pytest.fixture
def service() -> ActualStateService:
    engine = make_engine()
    create_schema(engine)
    return ActualStateService(engine, source_system="test")


@pytest.fixture
def demo_path() -> Path:
    return Path(__file__).parents[1] / "data/load_data/adventureworks_demo"
