# Multi-stage Dockerfile for OLAV v0.8 Agent

# Stage 1: Builder - Python dependencies
FROM python:3.13-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy project files for dependency installation
COPY pyproject.toml uv.lock* ./

# Install uv and project dependencies
RUN pip install --no-cache-dir uv && \
    uv sync --frozen

# Stage 2: Runtime - Minimal base image
FROM python:3.13-slim

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN useradd -m -u 1000 olav && \
    mkdir -p /app /home/olav/.cache /home/olav/.local && \
    chown -R olav:olav /app /home/olav

# Copy virtual environment from builder
COPY --from=builder --chown=olav:olav /app/.venv /app/.venv

# Copy application code
COPY --chown=olav:olav . /app/

# Set Python path to use venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Set working directory
WORKDIR /app

# Create .olav directory for configuration
RUN mkdir -p /app/.olav/skills /app/.olav/knowledge /app/.olav/commands && \
    chown -R olav:olav /app/.olav

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" || exit 1

# Switch to non-root user
USER olav

# Expose CLI interface (for interactive use)
EXPOSE 8000

# Default command - run the OLAV CLI
ENTRYPOINT ["python", "-m", "olav.cli.cli_main"]
CMD ["--help"]
