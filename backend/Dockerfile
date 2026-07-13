FROM python:3.12-slim

# Build tooling required for bcrypt / cryptography wheels (P35); curl for the
# backend service healthcheck (17-worker-and-scheduling.md P3.4).
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    python3-dev \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic

RUN mkdir -p /app/data

EXPOSE 8000
# Default standalone entrypoint (workers hardcoded for a bare `docker run`).
# Both compose files override `command:` — dev pins --workers 1 (see
# SCHEDULER_IN_APP), prod uses WEB_CONCURRENCY, and the dedicated worker
# service overrides it entirely to `python -m app.worker`
# (17-worker-and-scheduling.md P3.4).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
