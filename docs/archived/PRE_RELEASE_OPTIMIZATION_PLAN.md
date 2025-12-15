# OLAV Pre-Release Optimization Plan

**Version**: v0.5.0-beta  
**Date**: 2025-12-08  
**Status**: Planning

---

## Overview

This document outlines the optimization tasks required before the official release of OLAV (NetAIChatOps).

---

## 1. Branding Update: OLAV → NetAIChatOps

### Current State
- "Omni-Layer Autonomous Verifier" appears in 13 files
- Locations: `pyproject.toml`, `README.md`, `src/olav/__init__.py`, `src/olav/main.py`, `src/olav/cli/display.py`, `src/olav/server/app.py`, `.github/copilot-instructions.md`

### Target State
- **Short name**: OLAV (command name, package name)
- **Full name**: NetAIChatOps
- Remove all "Omni-Layer Autonomous Verifier" references

### Files to Update
| File | Change |
|------|--------|
| `pyproject.toml` | `description = "OLAV (NetAIChatOps)"` |
| `README.md` | Update title and footer |
| `src/olav/__init__.py` | Update docstring |
| `src/olav/main.py` | Update help text |
| `src/olav/cli/display.py` | Update banner subtitle |
| `src/olav/server/app.py` | Update API description |
| `.github/copilot-instructions.md` | Update project overview |
| `docs/*.md` | Update references |

### Effort
- **Estimate**: 1 hour
- **Priority**: P0

---

## 2. CLI Entry Point Redesign

### Current State
```bash
uv run olav              # Dashboard (TUI)
uv run olav -q "query"   # Single query
```

### Target State
```bash
uv run olav              # Dashboard (Rich TUI with status panels)
uv run olav cli          # Interactive REPL mode
uv run olav query "xxx"  # Single query (script-friendly)
```

### Implementation
- Add `cli` subcommand to `src/olav/cli/commands.py`
- Keep `query` as existing subcommand
- Default (no args) → Dashboard

### Effort
- **Estimate**: 2 hours
- **Priority**: P2

---

## 3. Read-Write vs Read-Only Token Permissions

### Current State
- Single `admin` role for all authenticated users
- No permission differentiation
- `auth.py` line 101: `return (True, {"username": "admin", "role": "admin", ...})`

### Target State

#### User Roles
```python
class UserRole(str, Enum):
    ADMIN = "admin"       # Full access, no HITL required
    OPERATOR = "operator" # Read-write with HITL confirmation
    VIEWER = "viewer"     # Read-only, cannot trigger write workflows
```

#### Permission Matrix
| Workflow | Admin | Operator | Viewer |
|----------|-------|----------|--------|
| QueryDiagnostic (read) | ✅ | ✅ | ✅ |
| DeviceExecution (write) | ✅ | ✅ (HITL) | ❌ |
| NetBoxManagement (write) | ✅ | ✅ (HITL) | ❌ |
| DeepDive (expert mode) | ✅ | ✅ | ❌ |

### Implementation Files
- `src/olav/server/auth.py` - Add `UserRole` enum, update `create_session()`
- `src/olav/agents/root_agent_orchestrator.py` - Check role before workflow routing
- `src/olav/server/app.py` - Token generation with role parameter

### Token Structure
```python
class SessionToken(BaseModel):
    token: str
    client_id: str
    client_name: str
    role: UserRole  # NEW: Add role field
    created_at: datetime
    expires_at: datetime
```

### Effort
- **Estimate**: 4 hours
- **Priority**: P1

---

## 4. Server-Side Token Management Tool

### Current State
- CLI includes `register` command that calls server API
- Token auto-saved to `~/.olav/credentials`
- Master token must be passed to client (security risk)

### Target State

#### New Admin CLI Tool
```bash
# Server-side management (admin only)
uv run olav-admin token create --role operator --name "alice-laptop"
uv run olav-admin token list
uv run olav-admin token revoke <client_id>
uv run olav-admin device init --from-netbox
uv run olav-admin index rebuild
```

#### Client Workflow
1. Admin generates token via `olav-admin token create`
2. Admin shares token with user (secure channel)
3. User sets `OLAV_API_TOKEN=<token>` in their environment
4. User runs `uv run olav cli`

### Implementation
- Create `src/olav/admin/` module
- Add entry point: `olav-admin = "olav.admin.commands:app"`
- Remove `register` command from CLI (security)
- Keep token validation logic in `auth.py`

### Effort
- **Estimate**: 4 hours
- **Priority**: P1

---

## 5. Standalone CLI Client Distribution

### Current State
- `cli.py` in root (wrapper)
- Actual implementation in `src/olav/cli/`
- Requires full package installation

### Target State

#### Option A: Single-file Client (Recommended)
```
olav-client/
├── olav_client.py      # Single-file thin client (~500 lines)
├── requirements.txt    # httpx, rich, prompt-toolkit
└── README.md           # Usage instructions
```

Features:
- No olav package installation required
- User configures `SERVER_URL` and `TOKEN` only
- Copy to any terminal and run

#### Option B: PyPI Package
```bash
pip install olav-client
olav-client --server http://server:8000 --token xxx
```

### Effort
- **Estimate**: 3 hours
- **Priority**: P2

---

## 6. Configuration File Consolidation

### Current State
| File | Purpose | Location |
|------|---------|----------|
| `.env` | Secrets (API keys, passwords) | Root |
| `config/olav.yaml` | Model config, feature flags | config/ |
| `config/settings.py` | Path definitions, hardcoded defaults | config/ |
| `src/olav/core/settings.py` | Pydantic .env loader | src/ |

### Problems
- Two `settings.py` files cause confusion
- YAML and .env have duplicate config items
- No single source of truth

### Target State
```
config/
├── .env                    # Secrets ONLY (API keys, passwords)
├── olav.yaml               # All application config (merge settings.py)
├── prompts/                # Prompt templates
├── inspections/            # Inspection configs
└── rules/                  # Rule files
```

### Loading Priority
1. Environment variables (Docker/CI override)
2. `config/.env` (secrets)
3. `config/olav.yaml` (application config)
4. Code defaults

### Changes
- Delete `config/settings.py` → merge into `olav.yaml`
- Keep `src/olav/core/settings.py` as single loader
- Update all imports

### Effort
- **Estimate**: 3 hours
- **Priority**: P1

---

## 7. Quick Start Flow Optimization

### Current Flow (Too Complex)
```bash
# 1. Clone repository
git clone ...
cd Olav

# 2. Install dependencies
uv sync --dev

# 3. Copy config files
cp .env.example .env
cp config/olav.example.yaml config/olav.yaml
# Edit .env with API keys...

# 4. Start containers
docker-compose up -d opensearch postgres redis

# 5. Initialize
uv run olav --init

# 6. (Optional) Start NetBox
docker-compose --profile netbox up -d

# 7. Start server
docker-compose up -d olav-server

# 8. Get token (from server logs)
docker-compose logs olav-server | grep "Token:"

# 9. Start CLI
uv run olav
```

### Target Flow
```bash
# 1. One-command Quick Start
git clone ... && cd Olav
make quickstart

# quickstart automatically:
# - Detects .env, copies from .env.example if missing
# - Detects Docker, starts required containers
# - Waits for container health
# - Runs --init initialization
# - Generates and displays temporary token
# - Shows next steps

# 2. (Optional) Full Deployment
make deploy              # With NetBox + server
```

### Makefile Implementation
```makefile
.PHONY: quickstart deploy init doctor

quickstart:
	@echo "🚀 OLAV Quick Start..."
	@test -f .env || cp .env.example .env
	docker-compose up -d opensearch postgres redis
	@echo "⏳ Waiting for services..."
	@sleep 15
	uv sync
	uv run olav --init
	@echo ""
	@echo "✅ Ready! Run: uv run olav"

deploy:
	docker-compose --profile netbox up -d
	@sleep 30
	uv run olav --init-netbox
	docker-compose up -d olav-server
	@echo "✅ Server running at http://localhost:8001"

doctor:
	uv run olav doctor
```

### New `doctor` Command
```bash
uv run olav doctor
# Output:
# ✅ PostgreSQL: connected
# ✅ OpenSearch: connected (3 indexes)
# ✅ Redis: connected
# ⚠️ NetBox: not configured
# ✅ LLM: ollama (qwen3:30b)
```

### Effort
- **Estimate**: 3 hours
- **Priority**: P0

---

## 8. Additional Optimizations

### 8.1 Version Management
- Current: `pyproject.toml` version = "0.1.0"
- Target: Sync with release version, auto-update `__version__`

### 8.2 Health Check Command
```bash
uv run olav doctor        # Check all dependency status
```

### 8.3 Unified Logging
- Current: Multiple `logging.basicConfig()` calls
- Target: Centralize in `src/olav/core/logging_config.py`

### 8.4 Error Message Standardization
- Current: Mixed Chinese/English error messages
- Target: All English, UI language controlled by `--lang`

### 8.5 Test Coverage Report
```bash
uv run pytest --cov=src/olav --cov-report=html
```

### 8.6 Pre-release Cleanup
- Archive or delete `archive/` unused code
- Update `README.md` quick start guide
- Add `CHANGELOG.md`
- Add `CONTRIBUTING.md`

### 8.7 Docker Image Optimization
- Current Dockerfile is heavy
- Consider multi-stage build to reduce image size

---

## Priority Summary

| Priority | Task | Effort | Status |
|----------|------|--------|--------|
| P0 | 1. Branding Update | 1h | ✅ DONE |
| P0 | 7. Quick Start Optimization | 3h | ✅ DONE |
| P1 | 3. Read-Only Permission Design | 4h | ✅ DONE |
| P1 | 4. Server-Side Admin Tool | 4h | ✅ DONE |
| P1 | 6. Config File Consolidation | 3h | ✅ DONE |
| P2 | 2. CLI Entry Refactor | 2h | ✅ DONE |
| P2 | 5. Standalone Client Distribution | 3h | ✅ DONE |
| P2 | 8. Additional Optimizations | 2h | ✅ DONE |

**Total Estimate**: ~22 hours

---

## Implementation Order

### Phase 1: Quick Wins (Day 1)
1. ✅ Branding update (OLAV → NetAIChatOps)
2. ✅ Update Makefile with `quickstart` target
3. ✅ Add `doctor` command

### Phase 2: Security (Day 2-3)
4. Implement UserRole enum and permission matrix
5. Create `olav-admin` tool
6. Remove `register` from CLI

### Phase 3: Configuration (Day 4)
7. Consolidate config files
8. Update documentation

### Phase 4: Polish (Day 5)
9. CLI entry point refactor
10. Standalone client extraction
11. Final testing and cleanup

---

## Testing Checklist

- [ ] All unit tests pass (`uv run pytest tests/unit/`)
- [ ] E2E tests pass (`uv run pytest tests/e2e/`)
- [ ] `make quickstart` works on clean environment
- [ ] Token permissions enforced correctly
- [ ] `olav-admin` commands work
- [ ] Standalone client connects successfully
- [ ] README quick start guide accurate
