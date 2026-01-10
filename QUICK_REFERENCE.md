# OLAV v0.8 Quick Reference Guide

**Status**: ✅ PRODUCTION READY | 229/229 Tests Passing (100%)  
**Last Updated**: 2026-01-10  
**Version**: 0.8.1

---

## Phase Completion Summary

| Phase | Focus | Tests | Status | Docs |
|-------|-------|-------|--------|------|
| **A** | Core Agent Architecture | 47 | ✅ | [DESIGN_V0.81.md](docs/DESIGN_V0.81.md#phase-a) |
| **B** | DeepAgents Integration | 57 | ✅ | [DESIGN_V0.81.md](docs/DESIGN_V0.81.md#phase-b) |
| **C-1** | Configuration Management | 30 | ✅ | [PHASE_C4_COMPLETION.md](docs/PHASE_C4_COMPLETION.md) |
| **C-2** | CLI Commands Enhancement | 32 | ✅ | [PHASE_C4_COMPLETION.md](docs/PHASE_C4_COMPLETION.md) |
| **C-3** | Claude Code Migration | 22 | ✅ | [PHASE_C4_COMPLETION.md](docs/PHASE_C4_COMPLETION.md) |
| **C-4** | Deployment & Containerization | 41 | ✅ | [DEPLOYMENT.md](docs/DEPLOYMENT.md) |
| **TOTAL** | **All Phases** | **229** | **✅** | [OLAV_V0.8_COMPLETE_SUMMARY.md](docs/OLAV_V0.8_COMPLETE_SUMMARY.md) |

---

## Quick Start (Choose One)

### 1️⃣ Docker Compose (5 minutes - Recommended for Development)
```bash
# Start full stack locally
docker-compose up -d

# View logs
docker-compose logs -f olav-agent

# Run CLI
docker exec -it olav-agent python -m olav.cli.cli_main --help

# Stop
docker-compose down
```

### 2️⃣ Kubernetes (15 minutes - For Production)
```bash
# Deploy to cluster
kubectl apply -f k8s/olav-deployment.yaml

# Monitor deployment
kubectl get pods -n olav -w

# View logs
kubectl logs -n olav -l app=olav -f

# Scale to 3 replicas
kubectl scale deployment olav-agent -n olav --replicas=3
```

### 3️⃣ Docker Single Container (2 minutes)
```bash
# Build image
docker build -t olav:0.8 .

# Run container
docker run -d -v $(pwd)/.olav:/app/.olav olav:0.8

# View logs
docker logs -f <container-id>
```

---

## Key Architecture

### Three-Layer System
```
┌─────────────────────────────────────┐
│ Skills (.olav/skills/*.md)          │  ← HOW: Strategies & SOPs
├─────────────────────────────────────┤
│ Knowledge (.olav/knowledge/*.md)    │  ← WHAT: Facts & Context
├─────────────────────────────────────┤
│ Capabilities (Python/DB)            │  ← CAN: Execution & Tools
└─────────────────────────────────────┘
```

### Runtime Stack
- **Agent**: DeepAgents + LangGraph (orchestration)
- **LLM**: Ollama (local inference)
- **Storage**: PostgreSQL (checkpoints) + Redis (cache)
- **Vector**: DuckDB (embeddings)
- **Network**: Nornir (automation)

---

## Configuration

### Basic Setup
```bash
# Copy template
cp .olav/settings.json .olav/settings.json.local

# Edit configuration
vi .olav/settings.json

# Validate
uv run python verify_config.py
```

### Environment Variables
```bash
# Create .env file
cat > .env << EOF
OPENAI_API_KEY=your-key-here
POSTGRES_PASSWORD=secure-password
REDIS_PASSWORD=secure-password
EOF

# Load
source .env  # Linux/Mac
# or
.\.env  # Windows PowerShell
```

---

## Testing

### Run All Tests
```bash
# All 229 tests
uv run pytest

# Only Phase C tests
uv run pytest tests/test_settings_configuration.py \
               tests/test_cli_commands_c2.py \
               tests/test_claude_migration_c3.py \
               tests/test_deployment_c4.py -v

# With coverage
uv run pytest --cov=src/olav --cov-report=html
```

### Validate Deployment
```bash
# Docker
docker build -t olav:0.8 .

# Docker Compose
docker-compose config
docker-compose up --no-start
docker-compose start

# Kubernetes
kubectl apply -f k8s/olav-deployment.yaml --dry-run=client
kubectl apply -f k8s/olav-deployment.yaml
```

---

## Important Directories

| Path | Purpose |
|------|---------|
| `.olav/` | Configuration directory (Skills, Knowledge, Settings) |
| `.claude/` | Claude Code compatibility (auto-synced from .olav) |
| `src/olav/` | Python implementation |
| `tests/` | Test suite (229 tests) |
| `docs/` | Documentation (2,500+ lines) |
| `k8s/` | Kubernetes manifests |

---

## Essential Commands

### Configuration
```bash
olav config show                    # Show all settings
olav config set key value          # Change setting
olav config validate               # Validate configuration
```

### Skills
```bash
olav skill list                     # List all skills
olav skill show <skill_id>         # Show skill details
olav skill search <query>          # Search skills
```

### Knowledge
```bash
olav knowledge list                 # List knowledge
olav knowledge search <query>      # Search knowledge
olav knowledge add-solution <name> # Add solution
```

### System
```bash
olav system info                    # System information
olav system health                  # Health check
olav system validate                # Full validation
```

---

## Deployment Options

### Development
- **Environment**: Local machine / laptop
- **Tool**: Docker Compose
- **Time**: 5 minutes
- **Scale**: Manual (1 instance)
- **Persistence**: Local volumes

### Testing
- **Environment**: Single server / VM
- **Tool**: Docker or Docker Compose
- **Time**: 5-10 minutes
- **Scale**: Manual (configure replicas)
- **Persistence**: Volume mounts

### Production
- **Environment**: Kubernetes cluster
- **Tool**: kubectl
- **Time**: 15 minutes
- **Scale**: Automatic (HPA 1-3 replicas)
- **Persistence**: Persistent volumes

---

## Troubleshooting

### Container Won't Start
```bash
# Check logs
docker logs <container-id>
docker-compose logs olav-agent

# Verify configuration
docker exec <container-id> python -m olav.cli.cli_main --health

# Rebuild
docker build --no-cache -t olav:0.8 .
```

### Kubernetes Pod Issues
```bash
# Check pod status
kubectl describe pod -n olav <pod-name>

# View logs
kubectl logs -n olav <pod-name> -c olav-agent

# Check readiness
kubectl get pods -n olav -o jsonpath='{.items[*].status.conditions[?(@.type=="Ready")]}'

# Manual restart
kubectl rollout restart deployment olav-agent -n olav
```

### Configuration Errors
```bash
# Validate configuration
uv run python verify_config.py

# Reset to defaults
rm .olav/settings.json
docker exec <container-id> python -m olav.cli.cli_main --init-config
```

---

## Performance Tuning

### Docker Compose
```yaml
# Adjust in docker-compose.yml
services:
  olav-agent:
    deploy:
      resources:
        limits:
          cpus: '4'        # Increase from 2
          memory: 4G       # Increase from 2G
```

### Kubernetes
```bash
# Scale manually
kubectl scale deployment olav-agent -n olav --replicas=5

# Update resource limits
kubectl set resources deployment olav-agent -n olav \
  --limits=cpu=2,memory=2Gi \
  --requests=cpu=1,memory=1Gi

# Check HPA status
kubectl get hpa -n olav
```

---

## Documentation Index

| Document | Purpose | Size |
|----------|---------|------|
| [DESIGN_V0.81.md](docs/DESIGN_V0.81.md) | Architecture & Design | 4,500 lines |
| [DEPLOYMENT.md](docs/DEPLOYMENT.md) | Deployment Guide | 600 lines |
| [OLAV_V0.8_COMPLETE_SUMMARY.md](docs/OLAV_V0.8_COMPLETE_SUMMARY.md) | Complete Summary | 800 lines |
| [PHASE_C4_COMPLETION.md](docs/PHASE_C4_COMPLETION.md) | Phase C-4 Details | 600 lines |
| [PHASE_C_FINAL_SUMMARY.md](docs/PHASE_C_FINAL_SUMMARY.md) | Phase C Overview | 800 lines |
| [CLI_USER_GUIDE.md](docs/CLI_USER_GUIDE.md) | CLI Reference | 400 lines |
| [TEST_GUIDE.md](TEST_GUIDE.md) | Testing Guide | 200 lines |

---

## Security Checklist

- [x] Non-root user (olav:1000)
- [x] No privilege escalation
- [x] RBAC with minimal permissions (K8s)
- [x] Secret management (env vars, K8s Secrets)
- [x] Health checks and monitoring
- [x] TLS-ready architecture
- [x] Network policies ready
- [x] Audit logging capable

---

## Production Readiness

| Aspect | Status | Details |
|--------|--------|---------|
| Code Quality | ✅ | 229/229 tests, 100% type hints |
| Documentation | ✅ | 2,500+ lines, comprehensive |
| Security | ✅ | Non-root, RBAC, secrets management |
| Scalability | ✅ | HPA (1-3 replicas), load balancing |
| Reliability | ✅ | Health checks, auto-restart, persistence |
| Operations | ✅ | CLI, troubleshooting guide, monitoring |

---

## Support & Links

- **GitHub Repository**: [OLAV](https://github.com/your-org/olav)
- **Documentation**: [docs/](docs/)
- **Issue Tracking**: GitHub Issues
- **Architecture**: [DESIGN_V0.81.md](docs/DESIGN_V0.81.md)
- **Deployment**: [DEPLOYMENT.md](docs/DEPLOYMENT.md)

---

## Next Steps

1. **Local Testing**: `docker-compose up -d` (5 min)
2. **Run Tests**: `uv run pytest` (2 min)
3. **Read Docs**: [DEPLOYMENT.md](docs/DEPLOYMENT.md) (20 min)
4. **Deploy**: Choose Docker, Compose, or K8s (5-15 min)
5. **Configure**: Update `.olav/settings.json` (5 min)
6. **Validate**: Run health checks and tests (5 min)

---

**OLAV v0.8 is production-ready!** 🚀

For detailed information, see the documentation index above.
