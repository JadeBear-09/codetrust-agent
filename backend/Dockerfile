# syntax=docker/dockerfile:1.7
FROM ghcr.io/astral-sh/uv:0.8.15 AS uv
FROM python:3.12.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN groupadd --system --gid 10001 tnoc \
    && useradd --system --uid 10001 --gid tnoc --home-dir /app tnoc

WORKDIR /app
COPY --from=uv /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY prompts ./prompts
COPY config ./config
COPY migrations ./migrations
COPY alembic.ini ./
RUN uv sync --frozen --no-dev \
    && chown -R tnoc:tnoc /app

USER 10001:10001
ENV PATH="/app/.venv/bin:${PATH}"
EXPOSE 8000
CMD ["tnoc-api"]
