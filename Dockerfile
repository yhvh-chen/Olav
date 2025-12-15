# ============================================
# OLAV Main Application Dockerfile
# ============================================
# Build: docker build -t olav-app:latest .
# Run:   docker run -p 8000:8000 --env-file .env olav-app:latest

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copy dependency files first (better layer caching)
COPY pyproject.toml uv.lock README.md ./

# Copy application code
COPY src ./src
COPY config ./config

# Install dependencies (production only, no dev deps)
RUN uv sync --frozen --no-dev

# Create non-root user for security
RUN useradd -m -u 1000 olav && chown -R olav:olav /app

# Create SuzieQ config directory
RUN mkdir -p /home/olav/.suzieq && chown -R olav:olav /home/olav/.suzieq
COPY --chown=olav:olav config/suzieq-cfg.yml /home/olav/.suzieq/suzieq-cfg.yml

USER olav

# Expose port for web service
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command (can be overridden)
CMD ["uv", "run", "python", "-m", "olav.main", "serve"]
