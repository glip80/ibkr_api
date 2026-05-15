FROM python:3.12-slim AS builder

WORKDIR /app

# Install uv
RUN pip install uv

# Copy dependency manifest
COPY pyproject.toml .
COPY README.md .

# Install dependencies (no dev extras)
RUN uv venv .venv && \
    uv pip install --no-cache --python .venv/bin/python .

# Copy source
COPY src/ src/
COPY alembic/ alembic/
COPY alembic.ini .

# Runtime image
FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /app /app

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH="/app/src"

# Run Alembic migrations then start the MCP server
ENTRYPOINT ["sh", "-c", "alembic upgrade head && ibkr-mcp"]