FROM python:3.13-slim AS development

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app


RUN apt-get update && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    libxml2-dev \
    libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .

RUN pip install --upgrade "pip>=26.1" --no-cache-dir && \
    pip install uv --no-cache-dir && \
    uv sync --all-extras --no-dev

RUN useradd --create-home appuser

COPY --chown=appuser:appuser alembic/ /app/alembic/
COPY --chown=appuser:appuser alembic.ini /app/
COPY --chown=appuser:appuser entrypoint.sh /app/
COPY --chown=appuser:appuser entrypoint-celery.sh /app/
COPY --chown=appuser:appuser src/ /app/src/
COPY --chown=appuser:appuser manage.py /app/

RUN chmod +x /app/entrypoint.sh /app/entrypoint-celery.sh

USER appuser

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]


FROM python:3.13-slim AS graphify

ARG GRAPHIFY_VERSION=0.9.18

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    GRAPHIFY_QUERY_LOG_DISABLE=1 \
    HOME=/tmp/graphify-home

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir "graphifyy[mcp]==${GRAPHIFY_VERSION}" \
    && mkdir -p /tmp/graphify-home \
    && chmod 1777 /tmp/graphify-home

WORKDIR /workspace

ENTRYPOINT ["graphify"]
