# ─────────────────────────────────────────────────────────────────
# Stage 1 – dependency installer
#   Uses uv to produce a clean venv at /app/.venv
#   Layer is cached as long as pyproject.toml + uv.lock don't change.
# ─────────────────────────────────────────────────────────────────
FROM python:3.13-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN pip install --no-cache-dir uv

WORKDIR /app

# Copy only the manifests first → maximises Docker layer cache
COPY pyproject.toml uv.lock ./

# Install production deps into an in-project venv
RUN uv sync --frozen --no-dev

# ─────────────────────────────────────────────────────────────────
# Stage 2 – runtime image
# ─────────────────────────────────────────────────────────────────
FROM python:3.13-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Make the venv's Python the default
    PATH="/app/.venv/bin:$PATH"

# curl for Docker healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Bring the pre-built venv from builder
COPY --from=builder /app/.venv .venv

# Copy application source
COPY app/ ./app/

# Volume mount-point for persistent SQLite + DuckDB files.
# Override paths with EARLY_ALERTS_STORAGE__SQLITE_PATH etc.
RUN mkdir -p /data

EXPOSE 8000

# Default command: API only (no scheduler).
# The scheduler service overrides this via docker-compose command:.
CMD ["uvicorn", "app.backend.main:app", \
    "--host", "0.0.0.0", \
    "--port", "8000", \
    "--workers", "1"]
