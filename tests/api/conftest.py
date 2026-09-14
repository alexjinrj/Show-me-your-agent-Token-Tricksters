from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from business_coordinator.api.app import create_app
from business_coordinator.api.settings import Settings

DEMO_DATA_DIR = Path(__file__).parents[2] / "data/demo/raw"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        db_path=tmp_path / "demo.db",
        host="127.0.0.1",
        host_port=8000,
        demo_data_dir=DEMO_DATA_DIR,
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client
