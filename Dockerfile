FROM python:3.12-slim AS builder

WORKDIR /app

# Install uv
RUN pip install uv

# Copy everything needed for the build
COPY pyproject.toml README.md uv.lock ./
COPY src/ src/
COPY alembic/ alembic/
COPY alembic.ini .

# Install all dependencies and the package itself
RUN uv venv .venv && \
    uv pip install --no-cache --python .venv/bin/python .

# Runtime image
FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /app /app

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH="/app/src"

# Run Alembic migrations then start the MCP server
ENTRYPOINT ["sh", "-c", "alembic upgrade head && ibkr-mcp"]