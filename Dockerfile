# One image, two processes: the API and (when LIVEKIT_URL is set) the voice agent.
# Each has its own venv, so their dependencies never conflict.

# ---- api builder: resolves the API dependencies into /app/.venv ----
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS api-builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project


# ---- voice: venv in /app/voice/.venv + VAD / turn detector weights ----
# Also the image of the `voice` service in docker-compose (target: voice).
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS voice

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    HF_HOME=/app/voice/.hf \
    PYTHONUNBUFFERED=1

WORKDIR /app/voice

COPY voice/pyproject.toml voice/uv.lock ./
RUN uv sync --frozen --no-dev

COPY voice/*.py ./
# Bakes the model weights into the image (no download at startup).
RUN .venv/bin/python agent.py download-files

CMD [".venv/bin/python", "agent.py", "start"]


# ---- runtime: both venvs + source only (no uv, no dev deps) ----
FROM python:3.13-slim-bookworm

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/app/voice/.hf \
    HF_HUB_OFFLINE=1

WORKDIR /app

RUN useradd --create-home --uid 1000 app

COPY --from=api-builder /app/.venv ./.venv
# Migrations run on startup (api.py -> alembic upgrade head).
COPY alembic.ini migrate.py ./
COPY migrations ./migrations
COPY src ./src

COPY --from=voice /app/voice/.venv ./voice/.venv
COPY --from=voice /app/voice/.hf ./voice/.hf
COPY voice/*.py ./voice/

COPY docker-entrypoint.sh ./
RUN chmod +x docker-entrypoint.sh

USER app

EXPOSE 3002

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:3002/health', timeout=4)"

CMD ["./docker-entrypoint.sh"]
