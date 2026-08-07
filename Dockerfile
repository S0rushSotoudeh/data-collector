ARG PYTHON_VERSION

FROM python:${PYTHON_VERSION}-slim AS development

ARG APP_PORT
ARG APP_USER
ARG PIP_PACKAGE
ARG UV_PACKAGE
ARG PYTHONUNBUFFERED
ARG PYTHONDONTWRITEBYTECODE

ENV PYTHONUNBUFFERED=${PYTHONUNBUFFERED} \
    PYTHONDONTWRITEBYTECODE=${PYTHONDONTWRITEBYTECODE} \
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

RUN pip install --upgrade "${PIP_PACKAGE}" --no-cache-dir && \
    pip install "${UV_PACKAGE}" --no-cache-dir && \
    uv sync --all-extras --no-dev

RUN useradd --create-home "${APP_USER}"

COPY --chown=${APP_USER}:${APP_USER} alembic/ /app/alembic/
COPY --chown=${APP_USER}:${APP_USER} alembic.ini /app/
COPY --chown=${APP_USER}:${APP_USER} entrypoint.sh /app/
COPY --chown=${APP_USER}:${APP_USER} entrypoint-celery.sh /app/
COPY --chown=${APP_USER}:${APP_USER} src/ /app/src/
COPY --chown=${APP_USER}:${APP_USER} manage.py /app/

RUN chmod +x /app/entrypoint.sh /app/entrypoint-celery.sh

USER ${APP_USER}

EXPOSE ${APP_PORT}

ENTRYPOINT ["/app/entrypoint.sh"]
