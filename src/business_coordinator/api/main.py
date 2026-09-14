from __future__ import annotations

from business_coordinator.api.app import create_app
from business_coordinator.api.settings import load_settings

# Module-level ASGI application for ``uvicorn business_coordinator.api.main:app``.
app = create_app()


def run() -> None:
    """Run the demo API with uvicorn using env-driven host/port settings."""
    import uvicorn

    settings = load_settings()
    uvicorn.run(
        "business_coordinator.api.main:app",
        host=settings.host,
        port=settings.host_port,
    )


if __name__ == "__main__":
    run()
