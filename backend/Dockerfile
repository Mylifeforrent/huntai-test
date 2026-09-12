# syntax=docker/dockerfile:1
#
# Backend image (Stage 12). Multi-stage: dependencies are resolved and the
# browser runtime is prepared in the builder, the runtime stage carries only the
# venv and the application layer.
#
# Build context is backend/. NEVER pass a build context that contains .env —
# .dockerignore excludes it, and config is injected as environment variables.

# ---- builder -----------------------------------------------------------------
FROM python:3.14-slim AS builder

# Pinned to the frozen tech-stack version (tech_stack_decision-v1.0.md §3.8).
COPY --from=ghcr.io/astral-sh/uv:0.12.7 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright

WORKDIR /app
# Dependency layer first: it only invalidates when the lockfile changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Chromium for the Playwright subprocess worker (M2 web execution). Browsers
# only here; the OS libraries are installed in the runtime stage.
RUN uv run --no-dev playwright install chromium

# ---- runtime -----------------------------------------------------------------
FROM python:3.14-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright

# The venv must be present first: install-deps resolves the playwright CLI from it.
COPY --from=builder /opt/venv /opt/venv

# Playwright's system libraries must live in the same image as the browsers.
RUN playwright install-deps chromium \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 appuser

COPY --from=builder /opt/ms-playwright /opt/ms-playwright

WORKDIR /app
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

# ARTIFACT_ROOT must point at a writable, persistent volume; this is only the
# in-image default so a bare `docker run` does not fail on first artifact write.
RUN mkdir -p /data/artifacts && chown -R appuser:appuser /data/artifacts /app

USER appuser
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import os,sys,urllib.request; port=os.environ.get('APP_PORT','8000'); sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{port}/healthz', timeout=2).status == 200 else 1)"

# Config is injected at runtime; nothing secret is baked into the image.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${APP_PORT:-8000}"]
