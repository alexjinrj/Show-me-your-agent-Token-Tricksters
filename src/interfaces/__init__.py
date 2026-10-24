"""Compat re-export: interfaces module has been moved to api/."""
from api.app import create_app  # noqa: F401
from api.settings import Settings, load_settings  # noqa: F401,F403
