# One image for every process (D-001): the command picks the role.
#   docker run IMAGE                 -> HTTP API on :8000 (default)
#   docker run IMAGE worker          -> scheduler + Telegram bot
#   docker run IMAGE migrate         -> alembic upgrade head
#   docker run IMAGE admin grant ID  -> bootstrap the first admin
# Configuration comes from environment variables (see .env.example), never baked into the image.

FROM ghcr.io/astral-sh/uv:0.12.9 AS uv

FROM python:3.14-slim AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app

# Dependencies first: this layer is reused until pyproject.toml / uv.lock change.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY alembic.ini ./
COPY migrations ./migrations
COPY src ./src
# Editable install keeps alembic.ini and migrations/ next to the package (src/cli.py finds them).
RUN uv sync --locked --no-dev


FROM python:3.14-slim
LABEL org.opencontainers.image.source="https://github.com/TJAkalit/reminder-backend" \
      org.opencontainers.image.description="Reminder habit tracker: API, scheduler and Telegram bot"

RUN useradd --system --uid 10001 --home-dir /app --shell /usr/sbin/nologin reminder
WORKDIR /app
COPY --from=build --chown=reminder:reminder /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    API_HOST=0.0.0.0 \
    API_PORT=8000
USER reminder
EXPOSE 8000

ENTRYPOINT ["reminder"]
CMD ["api"]
