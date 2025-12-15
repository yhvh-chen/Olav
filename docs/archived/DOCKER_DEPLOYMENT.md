# OLAV Docker Deployment Guide

## Quick Start (1 Minute)

### 1. Prerequisites
- Docker Desktop installed and running
- `.env` file configured (copy from `.env.example`)
- At minimum, set `LLM_API_KEY` in `.env`

### 2. Start All Services
```bash
# Build images
make build

# Start infrastructure + API server
make up

# Verify health
make health
```

### 3. Run E2E Tests
```bash
# Run full test suite
make test

# Run basic API tests only
make test-basic
```

Expected output:
```
Running E2E tests in container...
tests/e2e/test_api_basic.py::test_health_check PASSED
tests/e2e/test_api_basic.py::test_login_success PASSED
tests/e2e/test_api_basic.py::test_login_failure PASSED
tests/e2e/test_api_basic.py::test_me_endpoint_with_auth PASSED
tests/e2e/test_api_basic.py::test_me_endpoint_without_auth PASSED
tests/e2e/test_api_basic.py::test_status_endpoint PASSED

======================== 6 passed in 5.23s ========================
```

## Architecture

### Services Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Docker Network                        │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  PostgreSQL  │  │  OpenSearch  │  │    Redis     │  │
│  │   :5432      │  │    :9200     │  │    :6379     │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│         │                  │                  │         │
│         └──────────────────┴──────────────────┘         │
│                            │                            │
│                   ┌────────▼────────┐                   │
│                   │   OLAV API      │                   │
│                   │   :8000         │                   │
│                   └────────┬────────┘                   │
│                            │                            │
│                   ┌────────▼────────┐                   │
│                   │  OLAV Tests     │                   │
│                   │  (on-demand)    │                   │
│                   └─────────────────┘                   │
└─────────────────────────────────────────────────────────┘
```

### Container Details

#### 1. **olav-postgres**
- Image: `postgres:15-alpine`
- Persistent storage: `postgres_data` volume
- Health check: `pg_isready`
- Purpose: LangGraph checkpointer state storage

#### 2. **olav-opensearch**
- Image: `opensearchproject/opensearch:2.11.0`
- Persistent storage: `opensearch_data` volume
- Health check: Cluster health API
- Purpose: Schema indexes, memory indexes, document RAG

#### 3. **olav-redis**
- Image: `redis:7-alpine`
- Health check: `redis-cli ping`
- Purpose: Backend state storage (optional)

#### 4. **olav-api**
- Build: `Dockerfile.server`
- Health check: `/health` endpoint
- Depends on: postgres, opensearch, redis (all healthy)
- Purpose: Main API server with LangServe endpoints

#### 5. **olav-tests**
- Build: `Dockerfile.tests`
- Profile: `testing` (on-demand only)
- Depends on: olav-api (healthy)
- Purpose: E2E integration test execution

## Usage

### Production Deployment

```bash
# 1. Configure environment
cp .env.example .env
# Edit .env with production values

# 2. Build production images
docker-compose build

# 3. Start services
docker-compose up -d

# 4. Verify deployment
make health

# 5. View logs
docker-compose logs -f olav-api

# 6. Access API
curl http://localhost:8000/health
open http://localhost:8000/docs
```

### Development Mode

```bash
# Start with hot reload
make dev

# Or manually:
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up

# Features:
# - Source code mounted as volume
# - Auto-reload on file changes
# - Debug logging enabled
```

### Testing Workflow

#### Basic API Tests (No Orchestrator Required)
```bash
# Test authentication and basic endpoints
make test-basic

# Expected: 6/6 tests pass
# Tests: health, login success/failure, /me, /status
```

#### Full E2E Tests (With Orchestrator)
```bash
# Test complete workflow execution
make test

# Expected: 18/18 tests pass
# Includes: workflow invoke/stream, CLI client, LangServe SDK
```

#### Local Unit Tests
```bash
# Run unit tests on host machine
make test-unit

# Or with coverage:
uv run pytest tests/unit/ --cov=src/olav --cov-report=html
```

### Maintenance

#### View Logs
```bash
# All services
make logs

# API server only
make logs-api

# Specific service
docker-compose logs -f postgres
```

#### Restart Services
```bash
# Restart all
make restart

# Restart specific service
docker-compose restart olav-api
```

#### Shell Access
```bash
# API container
make shell-api

# Test container
make shell-tests

# Database
docker-compose exec postgres psql -U olav -d olav
```

#### Clean Up
```bash
# Stop and remove containers
make down

# Remove containers + volumes (WARNING: deletes data)
make clean

# Remove unused Docker resources
docker system prune -a
```

## Configuration

### Environment Variables

Required in `.env`:
```bash
# LLM Configuration (REQUIRED)
LLM_PROVIDER=openai
LLM_API_KEY=sk-...
LLM_MODEL_NAME=gpt-4-turbo

# JWT Security (Generate secure key for production)
JWT_SECRET_KEY=your-secret-key-min-32-chars

# Optional: NetBox integration
NETBOX_URL=https://netbox.company.com
NETBOX_TOKEN=your-netbox-token

# Optional: Feature flags
OLAV_USE_DYNAMIC_ROUTER=false
OLAV_EXPERT_MODE=false
```

### Port Mapping

| Service | Container Port | Host Port | Purpose |
|---------|---------------|-----------|---------|
| PostgreSQL | 5432 | 5432 | Database |
| OpenSearch | 9200 | 9200 | Search/Indexing |
| Redis | 6379 | 6379 | Cache |
| API Server | 8000 | 8000 | HTTP API |

### Volume Persistence

| Volume | Purpose | Size (typical) |
|--------|---------|----------------|
| `postgres_data` | Checkpointer state | 100MB-1GB |
| `opensearch_data` | Indexes (schema, memory, docs) | 500MB-5GB |

## Troubleshooting

### Service Won't Start

```bash
# Check status
docker-compose ps

# View logs for specific service
docker-compose logs postgres

# Verify dependencies
make health
```

### API Server Initialization Errors

```bash
# Common issue: LLM API key not set
# Solution: Check .env file

# View API logs
docker-compose logs olav-api

# Expected successful startup:
# ✅ Workflow Orchestrator ready (expert_mode=False)
# 🎉 OLAV API Server is ready!
```

### Tests Failing

```bash
# Ensure API is healthy first
make health

# Run basic tests to isolate issue
make test-basic

# If basic tests pass but full tests fail:
# - Check LLM_API_KEY is valid
# - Ensure OpenAI API is accessible
# - Verify PostgreSQL checkpointer initialized
```

### Database Connection Issues

```bash
# Check PostgreSQL is healthy
docker-compose exec postgres pg_isready -U olav

# View tables
docker-compose exec postgres psql -U olav -d olav -c "\dt"

# Should show:
# - checkpoints
# - checkpoint_writes
# - checkpoint_migrations
```

### Out of Memory

```bash
# Increase Docker Desktop memory limit
# Settings -> Resources -> Memory: 8GB recommended

# Or reduce OpenSearch memory:
# In docker-compose.yml:
OPENSEARCH_JAVA_OPTS=-Xms256m -Xmx256m
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: E2E Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Create .env
        run: |
          echo "LLM_API_KEY=${{ secrets.OPENAI_API_KEY }}" >> .env
          echo "JWT_SECRET_KEY=${{ secrets.JWT_SECRET }}" >> .env
      
      - name: Build images
        run: docker-compose build
      
      - name: Start services
        run: docker-compose up -d
      
      - name: Wait for health
        run: |
          timeout 60 bash -c 'until curl -f http://localhost:8000/health; do sleep 2; done'
      
      - name: Run tests
        run: docker-compose --profile testing run --rm olav-tests
      
      - name: Cleanup
        if: always()
        run: docker-compose down -v
```

## Performance Optimization

### Build Performance

```bash
# Use BuildKit for faster builds
export DOCKER_BUILDKIT=1
docker-compose build

# Multi-stage builds (already configured in Dockerfiles)
# - Separate dependency installation from code copy
# - Better layer caching
```

### Runtime Performance

```bash
# Production optimizations in docker-compose.yml:
# - restart: unless-stopped (auto-restart on failures)
# - healthchecks with appropriate intervals
# - Resource limits (can be added):

services:
  olav-api:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G
        reservations:
          cpus: '1'
          memory: 2G
```

## Security Considerations

### Production Checklist

- [ ] Change `JWT_SECRET_KEY` from default
- [ ] Use secrets management (Docker secrets, Vault, etc.)
- [ ] Enable HTTPS with reverse proxy (Nginx, Traefik)
- [ ] Restrict network access (firewall rules)
- [ ] Run containers as non-root user (already configured)
- [ ] Scan images for vulnerabilities: `docker scan olav-api`
- [ ] Enable OpenSearch security plugin in production
- [ ] Use read-only file systems where possible
- [ ] Implement rate limiting (API gateway)
- [ ] Enable audit logging

### Network Isolation

```yaml
# docker-compose.yml already uses isolated network
networks:
  olav-network:
    driver: bridge
    internal: true  # Add for full isolation (no external access)
```

## Monitoring

### Health Checks

```bash
# API health
curl http://localhost:8000/health

# OpenSearch cluster
curl http://localhost:9200/_cluster/health?pretty

# PostgreSQL
docker-compose exec postgres pg_isready -U olav
```

### Metrics Collection

```yaml
# Add Prometheus exporter (example)
services:
  prometheus:
    image: prom/prometheus
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    ports:
      - "9090:9090"

  grafana:
    image: grafana/grafana
    ports:
      - "3000:3000"
```

## Next Steps

1. **Development**: Use `make dev` for local development with hot reload
2. **Testing**: Run `make test` after code changes
3. **Deployment**: Configure production `.env` and use `make up`
4. **Monitoring**: Set up health check dashboards
5. **Scaling**: Use Docker Swarm or Kubernetes for multi-node deployment

## Support

- **Documentation**: See `docs/API_USAGE.md` for API reference
- **Testing Guide**: See `docs/TESTING_API_DOCS.md`
- **Architecture**: See `README.MD` for system design
- **Issues**: Check `docs/TASK_10_IMPLEMENTATION_STATUS.md` for known issues
