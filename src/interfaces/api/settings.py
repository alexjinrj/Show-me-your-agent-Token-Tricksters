from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DB_PATH = "runtime_data/enterprise_state.db"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_HOST_PORT = 8000
DEFAULT_DEMO_DATA_DIR = "data/load_data/adventureworks_demo"
DEFAULT_CONFIG_DIR = "src/core/process_definitions"
DEFAULT_WEB_DIR = "frontend"


@dataclass(frozen=True)
class Settings:
    """Environment-driven configuration for the demo API.

    Defaults bind to localhost so a developer machine is never exposed; the
    container image overrides ``BC_HOST`` to ``0.0.0.0`` for the later AWS
    Lightsail migration (hooks only).
    """

    db_path: Path
    host: str
    host_port: int
    demo_data_dir: Path
    config_dir: Path = Path(DEFAULT_CONFIG_DIR)
    web_dir: Path = Path(DEFAULT_WEB_DIR)
    upload_token: str | None = None

    @property
    def database_url(self) -> str:
        from enterprise_state.database import sqlite_url

        return sqlite_url(self.db_path)


def _env_int(env: dict[str, str], name: str, default: int) -> int:
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc


def load_settings(environ: dict[str, str] | None = None) -> Settings:
    env = os.environ if environ is None else environ
    db_path = env.get("BC_DB_PATH", DEFAULT_DB_PATH).strip() or DEFAULT_DB_PATH
    host = env.get("BC_HOST", DEFAULT_HOST).strip() or DEFAULT_HOST
    demo_dir = env.get("BC_DEMO_DATA_DIR", DEFAULT_DEMO_DATA_DIR).strip() or DEFAULT_DEMO_DATA_DIR
    config_dir = env.get("BC_CONFIG_DIR", DEFAULT_CONFIG_DIR).strip() or DEFAULT_CONFIG_DIR
    web_dir = env.get("BC_WEB_DIR", DEFAULT_WEB_DIR).strip() or DEFAULT_WEB_DIR
    upload_token = env.get("BC_UPLOAD_TOKEN", "").strip() or None
    return Settings(
        db_path=Path(db_path),
        host=host,
        host_port=_env_int(dict(env), "BC_HOST_PORT", DEFAULT_HOST_PORT),
        demo_data_dir=Path(demo_dir),
        config_dir=Path(config_dir),
        web_dir=Path(web_dir),
        upload_token=upload_token,
    )
