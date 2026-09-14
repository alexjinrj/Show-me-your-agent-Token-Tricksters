# Business Coordinator demo image.
# Single deployable: FastAPI backend + static SPA. Env-var driven so it can be
# lifted to AWS Lightsail later (hooks only; no provisioning here).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

# Bind to all interfaces inside the container; the seeded SQLite lives on a
# writable path so restarts stay idempotent.
ENV BC_HOST=0.0.0.0 \
    BC_HOST_PORT=8000 \
    BC_DB_PATH=/data/demo_actual_state.db \
    BC_DEMO_DATA_DIR=/app/data/demo/raw \
    BC_CONFIG_DIR=/app/config/processes \
    BC_WEB_DIR=/app/web

# Install uv (fast, reproducible resolver).
COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /usr/local/bin/uv

WORKDIR /app

# Resolve dependencies first for better layer caching.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy only what the runtime needs.
COPY src/ ./src/
COPY web/ ./web/
COPY config/ ./config/
COPY data/demo ./data/demo
RUN uv sync --frozen --no-dev

RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8000

# /healthz is a lightweight container health check target.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,os,sys; \
    port=os.environ.get('BC_HOST_PORT','8000'); \
    sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{port}/healthz').status==200 else 1)"

# Bind 0.0.0.0:${BC_HOST_PORT:-8000} for Lightsail compatibility.
CMD ["sh", "-c", "uv run uvicorn business_coordinator.api.main:app --host 0.0.0.0 --port ${BC_HOST_PORT:-8000}"]
