from __future__ import annotations

from pathlib import Path

from interfaces.api.settings import load_settings


def test_defaults_bind_to_localhost() -> None:
    settings = load_settings({})
    assert settings.host == "127.0.0.1"
    assert settings.host_port == 8000
    assert settings.db_path == Path("runtime_data/enterprise_state.db")
    assert settings.demo_data_dir == Path("data/load_data/adventureworks_demo")
    assert settings.config_dir == Path("src/core/process_definitions")
    assert settings.web_dir == Path("frontend")


def test_env_overrides_applied(tmp_path: Path) -> None:
    settings = load_settings(
        {
            "BC_DB_PATH": str(tmp_path / "custom.db"),
            "BC_HOST": "0.0.0.0",
            "BC_HOST_PORT": "9001",
            "BC_DEMO_DATA_DIR": "/data/raw",
            "BC_CONFIG_DIR": "/src/core/process_definitions",
            "BC_WEB_DIR": "/web",
        }
    )
    assert settings.db_path == tmp_path / "custom.db"
    assert settings.host == "0.0.0.0"
    assert settings.host_port == 9001
    assert settings.demo_data_dir == Path("/data/raw")
    assert settings.config_dir == Path("/src/core/process_definitions")
    assert settings.web_dir == Path("/web")
    assert settings.database_url.startswith("sqlite+pysqlite:///")
