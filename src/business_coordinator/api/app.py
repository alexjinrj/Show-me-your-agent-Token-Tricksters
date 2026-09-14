from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request

from business_coordinator.api.context import DemoContext
from business_coordinator.api.encoding import DecimalJSONResponse
from business_coordinator.api.settings import Settings, load_settings


def get_context(request: Request) -> DemoContext:
    context = getattr(request.app.state, "context", None)
    if not isinstance(context, DemoContext):  # pragma: no cover - defensive
        raise RuntimeError("demo context is not initialized")
    return context


def create_app(settings: Settings | None = None) -> FastAPI:
    """Application factory for the Business Coordinator demo API."""
    resolved = settings if settings is not None else load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.context = DemoContext.bootstrap(resolved)
        yield

    app = FastAPI(
        title="Business Coordinator Demo",
        version="0.1.0",
        default_response_class=DecimalJSONResponse,
        lifespan=lifespan,
    )
    app.state.settings = resolved

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    from business_coordinator.api.routes_reference import router as reference_router

    app.include_router(reference_router)

    from business_coordinator.api.routes_sessions import router as sessions_router

    app.include_router(sessions_router)

    from business_coordinator.api.routes_simulation import router as simulation_router

    app.include_router(simulation_router)

    from business_coordinator.api.routes_assistant import router as assistant_router

    app.include_router(assistant_router)

    _mount_static(app, resolved.web_dir)

    return app


def _mount_static(app: FastAPI, web_dir: Path) -> None:
    from fastapi.staticfiles import StaticFiles

    if web_dir.is_dir():
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
