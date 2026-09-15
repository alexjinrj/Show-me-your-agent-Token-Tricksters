from pathlib import Path

import pytest

from enterprise_state.database import create_schema, make_engine
from enterprise_state.service import ActualStateService


@pytest.fixture
def service() -> ActualStateService:
    engine = make_engine()
    create_schema(engine)
    return ActualStateService(engine, source_system="test")


@pytest.fixture
def demo_path() -> Path:
    return Path(__file__).parents[1] / "data/load_data/adventureworks_demo"
