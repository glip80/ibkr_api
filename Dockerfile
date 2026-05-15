# ── Build stage ──────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN pip install --no-cache-dir hatchling

COPY pyproject.toml ./
COPY src/ ./src/

RUN pip install --no-cache-dir --prefix=/install .

# ── Runtime stage ────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="ibkr-mcp-service"
LABEL org.opencontainers.image.description="MCP service for IBKR market data"

# Create non-root user for security
RUN useradd -m -u 1000 appuser

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy source (needed for editable install resolution)
COPY src/ ./src/

# Persistent data directory
RUN mkdir -p /app/data && chown appuser:appuser /app/data

USER appuser

# Healthcheck — verifies the process is alive via a dummy stdio ping
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import ibkr_mcp; print('ok')" || exit 1

# Environment defaults (override via docker-compose or -e flags)
ENV IBKR_HOST=host.docker.internal \
    IBKR_PORT=7497 \
    IBKR_CLIENT_ID=10 \
    IBKR_TIMEOUT=30 \
    DB_PATH=/app/data/ibkr_cache.db \
    QUOTES_TTL_HOURS=1 \
    FUNDAMENTALS_TTL_HOURS=24 \
    SYNC_INTERVAL_SECONDS=3600 \
    LOG_LEVEL=INFO \
    LOG_FORMAT=json \
    MCP_SERVER_NAME=ibkr-mcp

CMD ["python", "-m", "ibkr_mcp.server"]
