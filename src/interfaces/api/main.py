from __future__ import annotations

from interfaces.api.app import create_app
from interfaces.api.settings import load_settings

# Module-level ASGI application for ``uvicorn interfaces.api.main:app``.
app = create_app()


def run() -> None:
    """Run the demo API with uvicorn using env-driven host/port settings."""
    import uvicorn

    settings = load_settings()
    uvicorn.run(
        "interfaces.api.main:app",
        host=settings.host,
        port=settings.host_port,
    )


if __name__ == "__main__":
    run()
