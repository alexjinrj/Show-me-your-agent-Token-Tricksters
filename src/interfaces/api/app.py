from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request

from interfaces.api.context import DemoContext
from interfaces.api.encoding import DecimalJSONResponse
from interfaces.api.settings import Settings, load_settings


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
        from interfaces.runtime import build_runtime

        app.state.runtime = build_runtime(app.state.context)
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

    from interfaces.api.routes_reference import router as reference_router

    app.include_router(reference_router)

    from interfaces.api.routes_sessions import router as sessions_router

    app.include_router(sessions_router)

    from interfaces.api.routes_simulation import router as simulation_router

    app.include_router(simulation_router)

    from interfaces.api.routes_assistant import router as assistant_router

    app.include_router(assistant_router)

    from interfaces.api.routes_crm import legacy_router as legacy_crm_router
    from interfaces.api.routes_crm import router as crm_router

    app.include_router(crm_router)
    app.include_router(legacy_crm_router)

    from interfaces.api.routes_modules import router as modules_router

    app.include_router(modules_router)

    from interfaces.api.routes_workbench import router as workbench_router

    app.include_router(workbench_router)

    _mount_static(app, resolved.web_dir)

    return app


def _mount_static(app: FastAPI, web_dir: Path) -> None:
    from fastapi.staticfiles import StaticFiles

    if web_dir.is_dir():
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="frontend")
