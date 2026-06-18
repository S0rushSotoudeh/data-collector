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
    uv sync --no-dev

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