from __future__ import annotations

from api.app import create_app
from api.settings import load_settings

# Module-level ASGI application for ``uvicorn api.main:app``.
app = create_app()


def run() -> None:
    """Run the demo API with uvicorn using env-driven host/port settings."""
    import uvicorn

    settings = load_settings()
    uvicorn.run(
        "api.main:app",
        host=settings.host,
        port=settings.host_port,
    )


if __name__ == "__main__":
    run()
