# Formline backend: FastAPI + engine + agents. Generated data is built into the image
# (deterministic from the seed), so a container starts serving immediately.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

COPY --from=ghcr.io/astral-sh/uv:0.10.9 /uv /usr/local/bin/uv

WORKDIR /app

# Dependencies first, so code changes don't re-install them.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN uv sync --frozen --no-dev

# Synthetic season (seed 2026) and the live match's overlays. Built with the fake model;
# overlays precomputed with Microsoft Foundry can be shipped in demo/ (see start.sh).
RUN .venv/bin/formline-gen generate --out /app/data \
 && .venv/bin/formline-gen overlays --data /app/data

COPY demo ./demo
COPY scripts/start.sh ./start.sh

# Run as a non-root user. Only the data dir needs to be writable (LLM cache, overlays);
# re-owning all of /app would duplicate every file into a new layer.
RUN useradd --create-home --uid 10001 formline && chown -R formline /app/data
USER formline

ENV DATA_DIR=/app/data PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"

CMD ["./start.sh"]
