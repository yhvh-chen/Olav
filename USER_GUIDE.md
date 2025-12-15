# OLAV (NetAIChatOps)

<div align="center">

```
   ____  _        ___     __
  / __ \| |      / \ \   / /
 | |  | | |     / _ \ \ / / 
 | |  | | |    / ___ \ V /  
 | |__| | |___/ ___ \ | |   
  \____/|_____/_/   \_\|_|  
                            
  NetAIChatOps CLI
```

**LangGraph Workflows + SuzieQ + NETCONF/gNMI + NetBox**

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2+-green.svg)](https://langchain-ai.github.io/langgraph/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

</div>

---

## 🚀 Quick Start

### Option A: Automated Setup (Windows)

This repo uses an env-driven setup: you edit `.env`, then run setup.

```powershell
# 1) Copy template and edit
Copy-Item .env.example .env
notepad .env

# Install Python deps (first time)
uv sync --dev

# 2) QuickTest (default, auth disabled)
.\setup.ps1

# 3) Start using
uv run olav
```

**Production mode**:

```powershell
# 1) Generate a secure token (optional, or use your own)
python -c "import secrets; print(secrets.token_urlsafe(32))"

# 2) Set OLAV_API_TOKEN in .env
notepad .env
# OLAV_MODE=production
# OLAV_API_TOKEN=<your-generated-token>

# 3) Install Python deps (first time)
uv sync --dev

# 4) Run setup
.\setup.ps1 -Mode Production

# 5) Register a client (persists server URL to ~/.olav/config.toml)
# Note: Use the SAME token you put in .env
$env:OLAV_API_TOKEN = '<your-token-from-.env>'
uv run olav register --name "my-laptop" --server http://127.0.0.1:18001

# 6) Start using
uv run olav
```

### Option B: Automated Setup (Linux/Mac)

```bash
# 1) Copy template and edit
cp .env.example .env
${EDITOR:-vi} .env

# Install Python deps (first time)
uv sync --dev

# Ensure setup is executable
chmod +x setup.sh

# 2) QuickTest (default, auth disabled)
./setup.sh

# 3) Start using
uv run olav
```

**Production mode**:

```bash
# 1) Generate a secure token
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# 2) Set OLAV_API_TOKEN in .env
${EDITOR:-vi} .env
# OLAV_MODE=production
# OLAV_API_TOKEN=<your-generated-token>

# 3) Run setup
./setup.sh --mode Production

# 4) Register a client
# Note: Use the SAME token you put in .env
export OLAV_API_TOKEN='<your-token-from-.env>'
uv run olav register --name "my-laptop" --server http://127.0.0.1:18001

# 5) Start using
uv run olav
```

## 🧪 Testing

OLAV includes comprehensive testing suites for performance and integration.

### Performance Testing

To benchmark the server's throughput and latency:

```bash
# Run load test (default: 50 concurrent users, 10s duration)
uv run tests/performance/load_test_script.py

# Expected results (Production mode):
# - RPS: ~40-50 (Windows Docker networking overhead)
# - Latency P50: <10ms
# - Success Rate: 100%
```

### Integration Testing

To verify end-to-end functionality:

```bash
# Run all integration tests
uv run pytest tests/integration

# Run specific test
uv run pytest tests/integration/test_api_server.py
```

### 2. Start Services

```bash
# Start core infrastructure services (PostgreSQL, OpenSearch)
docker-compose up -d

# With Redis cache (optional, for multi-instance deployments)
docker-compose --profile cache up -d

# With built-in NetBox
docker-compose --profile netbox up -d

# Full stack (all optional components)
docker-compose --profile full --profile netbox up -d
```

### 3. Initialize

```bash
# Check index status
uv run olav init status

# Initialize all infrastructure (PostgreSQL + all indexes)
uv run olav init all

# Or initialize specific components:
uv run olav init schema    # Schema indexes only (SuzieQ/OpenConfig/NetBox)
uv run olav init rag       # RAG indexes only (episodic memory, docs)
uv run olav init postgres  # PostgreSQL Checkpointer only

# Import devices from config/inventory.csv to NetBox
uv run olav init netbox
```

### 4. Client Authentication & Registration

OLAV supports two modes:

- **QuickTest** (`AUTH_DISABLED=true`): no registration required
- **Production** (`AUTH_DISABLED=false`): requires `OLAV_API_TOKEN` (Master Token) and client registration

**Step 1: Decide your Server URL**

Use the host port you set in `.env`:

- `OLAV_SERVER_PORT` → `http://127.0.0.1:<OLAV_SERVER_PORT>`

**Step 2 (Production only): Register Client (Get Session Token)**

```bash
# Register client (persists server URL to ~/.olav/config.toml)
export OLAV_API_TOKEN='<master-token-from-.env>'
uv run olav register --name "my-laptop" --server http://127.0.0.1:<OLAV_SERVER_PORT>

# Output:
# ✅ Registration successful!
#    Client ID: 550e8400-e29b-41d4-a716-446655440000
#    Client Name: my-laptop
#    Expires: 2025-12-17T20:13:17Z
#    Credentials saved to ~/.olav/credentials
```

**Step 3: Verify Connection**

```bash
# Check system health
uv run olav status

# Expected output:
# Server          │ ✅ Connected
# PostgreSQL      │ ✅ Connected
# OpenSearch      │ ✅ Connected
# NetBox          │ ✅ Connected (via Server API)

# Test query (auto-loads token from ~/.olav/credentials)
uv run olav -q "show version"
```

---

## 📦 Standalone Client CLI (Scheme B: `olav-client`)

If you want to distribute **only a lightweight CLI** (no local LangGraph/NetBox/OpenSearch dependencies), use the client subproject in [client/](client/).

Important: this repository contains **two** CLIs that both expose an `olav` command:

- **Full CLI (server package)**: `uv run olav ...` (uses this repo’s full dependency set)
- **Standalone client CLI**: `uv run --project client olav ...` (HTTP/SSE only)

### Run client CLI from this repo

```powershell
# From repository root
uv run --project client olav --help
uv run --project client olav register --name "my-laptop" --token "<master-token>" --server http://localhost:18001
uv run --project client olav status
uv run --project client olav -q "Query BGP status of R1"
```

### Install the client package (source install)

```powershell
cd client
python -m pip install .
olav --help
```

**Note**: 
- Session Token is stored in `~/.olav/credentials` and auto-loaded for all CLI operations.
- Health checks are performed by the Server API - CLI gets aggregated status via `/health/detailed` endpoint.
- All infrastructure services (PostgreSQL, OpenSearch, NetBox, LLM, etc.) are checked server-side.

### 5. Start Using

```bash
# Interactive Dashboard (default)
uv run olav

# Lightweight REPL mode
uv run olav repl

# Single query
uv run olav -q "Query BGP status of R1"

# Expert mode (complex diagnostics)
uv run olav -E -q "Audit security config of all border routers"

# TUI dashboard with batch queries
uv run olav dashboard -q "query1" -q "query2"
```

### 6. Administration (Server-Side)

```bash
# Create session tokens for clients
uv run olav-admin token create --name "alice-laptop" --role operator

# List active sessions
uv run olav-admin token list

# Revoke a session
uv run olav-admin token revoke <client_id>

# Initialize databases
uv run olav-admin init
```

---

## 📋 CLI Command Reference

### Main Command

```bash
olav [OPTIONS] COMMAND [ARGS]...
```

| Option | Description |
|--------|-------------|
| `-q, --query TEXT` | Single query text |
| `--server TEXT` | API Server URL (defaults to `OLAV_SERVER_URL` or `~/.olav/config.toml`; fallback: http://localhost:8001) |
| `-S, --standard` | Standard mode (default, fast path) |
| `-E, --expert` | Expert mode (Deep Dive recursive diagnostics) |
| `-v, --verbose` | Verbose output |
| `--status` | Check system status (deprecated - use 'olav status' command) |

### Subcommands

| Command | Description |
|---------|-------------|
| `init` | Initialize infrastructure and indexes |
| `register` | Register client to get Session Token |
| `status` | System health check via Server API (all components) |
| `query` | Execute single query |
| `dashboard` | Launch full-screen TUI dashboard |
| `repl` | Lightweight REPL mode |
| `session` | Manage authentication sessions |
| `inspect` | Network inspection commands |
| `report` | View inspection reports |
| `doc` | RAG document management |
| `config` | CLI configuration management |
| `version` | Version information (use --banner for ASCII art) |

### Init Commands

```bash
# Initialize all components (PostgreSQL + all indexes)
olav init all

# Initialize with force reset (delete and recreate indexes)
olav init all --force

# Initialize schema indexes only (preserves RAG data)
olav init schema
olav init schema --force    # Force reset

# Initialize RAG indexes only (preserves schema data)
olav init rag
olav init rag --force       # Force reset

# Initialize PostgreSQL Checkpointer
olav init postgres

# Import devices from config/inventory.csv to NetBox
olav init netbox
olav init netbox --force    # Force import even if devices exist

# Check current index status
olav init status
```

### Authentication Commands

```bash
# Register client (writes Session Token to ~/.olav/credentials; if --server is provided, also saves it to ~/.olav/config.toml)
olav register --name "client-name" --token "<master-token>" --server <url>

# Check status (uses saved server URL / OLAV_SERVER_URL unless overridden)
olav status
olav status --server <url>

# Session management
olav session clients   # List all clients (requires admin privileges)
olav session threads   # List conversation threads
olav session logout    # Logout current session
```

### Inspection Commands

```bash
# List inspection configurations
olav inspect list

# Run inspection (async)
olav inspect run <profile>

# Wait for completion
olav inspect run <profile> --wait

# Check job status
olav inspect status <job-id>
olav inspect jobs
```

### Report Commands

```bash
# List reports
olav report list

# View report
olav report show <report-id>

# Download report
olav report download <report-id> -o report.md
```

### Document Management

```bash
# List indexed documents
olav doc list

# Upload document
olav doc upload <file>

# Search documents
olav doc search "BGP configuration best practices"
```

---

## 🔐 Authentication & Token System

### Overview

OLAV uses a **two-tier token authentication mechanism** with role-based access control (RBAC):

| Token Type | Validity | Purpose | Storage | Scope |
|------------|----------|---------|---------|-------|
| **Master Token** (`OLAV_API_TOKEN`) | Configurable | Client registration + admin APIs | `.env` (Production) | Server-level |
| **Session Token** | Configurable | Regular client operations | `~/.olav/credentials` | User-level |

### Token Generation & Lifecycle

#### Master Token

**Recommended (Production)**: set a fixed `OLAV_API_TOKEN` in `.env` and run setup in Production mode.

**Generate a token** (examples):

```bash
# Linux/Mac
uv run python -c "import secrets; print(secrets.token_urlsafe(32))"
```

```powershell
# Windows PowerShell
uv run python -c "import secrets; print(secrets.token_urlsafe(32))"
```

**Usage**:
- Used by admins for client registration
- Used for admin-level API operations
- Can be set via environment variable or .env file

**QuickTest**: keep `AUTH_DISABLED=true` and skip registration.

#### Session Token

**Generation** (via client registration):
```bash
# Register client with Master Token
uv run olav register \
  --name "alice-laptop" \
  --server http://127.0.0.1:<OLAV_SERVER_PORT>

# Session Token automatically saved to ~/.olav/credentials
```

**Storage Location**:
```bash
# Linux/Mac
~/.olav/credentials

# Windows
C:\Users\{username}\.olav\credentials

# Format (key=value pairs)
OLAV_SESSION_TOKEN=xyz789abc...
OLAV_CLIENT_ID=550e8400-e29b-41d4-a716-446655440000
OLAV_CLIENT_NAME=alice-laptop
```

**Auto-loading**: CLI automatically loads token from `~/.olav/credentials` for all operations.

### Token Lookup Priority

CLI searches for tokens in this order:

```python
1. OLAV_API_TOKEN environment variable     # Temporary override
2. OLAV_API_TOKEN from .env file           # Project-level config
3. OLAV_SESSION_TOKEN from ~/.olav/credentials  # User-level (recommended)
```

### Authentication Modes

#### Development Mode (Default)

```yaml
# docker-compose.yml
environment:
  AUTH_DISABLED: true  # No authentication required
```

**Behavior**:
- CLI connects without any token
- All requests treated as admin
- **Security**: ❌ Unsafe - for local dev only

#### Production Mode

```yaml
# docker-compose.yml (or .env)
environment:
  AUTH_DISABLED: false  # Authentication required
  OLAV_API_TOKEN: <master-token>
```

**Behavior**:
- CLI requires Session Token (from registration)
- Bearer token validated on every request
- Role-based access control enforced
- **Security**: ✅ Secure - required for production

### Role-Based Access Control (RBAC)

| Role | Read | Write (with HITL) | Write (no HITL) | Workflows |
|------|------|-------------------|-----------------|-----------|
| **admin** | ✅ | ✅ | ✅ | All |
| **operator** | ✅ | ✅ | ❌ | All (HITL required) |
| **viewer** | ✅ | ❌ | ❌ | Read-only workflows |

**Assign Role** (during registration):
```bash
uv run olav register --name "viewer-client" --role viewer --token "<master-token>"
```

### Token Validity Configuration

Set in `.env` or environment variables:

```bash
# Master Token validity (hours)
TOKEN_MAX_AGE_HOURS=48

# Session Token validity (hours)  
SESSION_TOKEN_MAX_AGE_HOURS=720  # 30 days
```

### Authentication Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                     Server Initialization                        │
│  1. QuickTest: AUTH_DISABLED=true (no auth)                      │
│  2. Production: AUTH_DISABLED=false + OLAV_API_TOKEN set         │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Client Registration (Production)             │
│  $ olav register --name "laptop" --server http://127.0.0.1:PORT  │
│                                                                  │
│  POST /auth/register                                            │
│  Request: {client_name, master_token, role}                      │
│  Response: {session_token, client_id, expires_at}              │
│                                                                  │
│  Saved to: ~/.olav/credentials                                  │
│    OLAV_SESSION_TOKEN=xyz789abc...                              │
│    OLAV_CLIENT_ID=550e8400-e29b-41d4-a716-446655440000         │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                     API Request Flow                             │
│  $ olav query "show interfaces"                                 │
│                                                                  │
│  1. CLI reads ~/.olav/credentials                               │
│  2. Adds header: Authorization: Bearer xyz789abc...             │
│  3. Server validates Session Token                              │
│  4. Checks role permissions                                     │
│  5. Executes query (with HITL if needed)                        │
└─────────────────────────────────────────────────────────────────┘
```

### Credential Files Structure

```
~/.olav/                           # User-level OLAV directory
├── credentials                     # Session Token (from register)
│   ├── OLAV_SESSION_TOKEN=xyz...
│   ├── OLAV_CLIENT_ID=550e8400...
│   └── OLAV_CLIENT_NAME=laptop
│
└── config.toml                     # Optional: Server URL config
    └── [server]
        url = "http://192.168.1.100:8001"
        timeout = 300
```

---

## 🌐 CLI Cross-Host Deployment

### Overview

OLAV CLI is a **thin client** - it only communicates with the server via HTTP/SSE. No server-side code or configuration files are needed on client hosts.

### What You Need

| Component | Required | Storage Location | Notes |
|-----------|----------|-----------------|-------|
| **CLI Code** | ✅ Yes | `/opt/olav-cli/` or anywhere | `cli.py` + `src/olav/cli/` |
| **Session Token** | ✅ Yes | `~/.olav/credentials` | Auto-generated after registration |
| **Server URL** | ✅ Yes | `~/.olav/config.toml` or env var | Where to connect |
| **.env file** | ❌ **No** | N/A | Server config only, NOT for client |
| **Dependencies** | ✅ Yes | Python venv | `uv sync` installs |

### Deployment Steps

#### Step 1: Prepare CLI Package (on Server Host)

```bash
# Option A: Copy from existing installation
mkdir olav-cli-package
cp cli.py olav-cli-package/
cp -r src/olav/cli olav-cli-package/src/olav/
cp pyproject.toml olav-cli-package/

# Option B: Git sparse checkout (if using Git)
git clone --filter=blob:none --sparse <repo-url>
cd olav
git sparse-checkout set cli.py src/olav/cli pyproject.toml
```

#### Step 2: Transfer to Client Host

```bash
# Linux/Mac
scp -r olav-cli-package user@client-host:/opt/olav-cli

# Windows
# Use WinSCP, RoboCopy, or PowerShell:
# robocopy olav-cli-package \\client-host\C$\opt\olav-cli /E
```

#### Step 3: Install Dependencies (on Client Host)

```bash
cd /opt/olav-cli
uv sync  # Installs only CLI dependencies (no server deps)
```

#### Step 4: Configure Server URL (on Client Host)

```bash
# Option A: Using config file (recommended)
mkdir -p ~/.olav
cat > ~/.olav/config.toml << EOF
[server]
url = "http://192.168.1.100:8001"  # Replace with actual server IP
timeout = 300
EOF

# Tip: If you run `olav register --server ...` once, the CLI can write this file for you.

# Option B: Using environment variable
export OLAV_SERVER_URL="http://192.168.1.100:8001"

# Option C: Using CLI argument (per-command)
uv run olav --server http://192.168.1.100:8001 query "test"
```

#### Step 5: Register Client (on Client Host)

```bash
# Production only: get Master Token from the server host's .env
# (server host)
cat .env | grep '^OLAV_API_TOKEN='

# Register client (on client host)
uv run olav register \
  --name "$(hostname)-client" \
  --server http://192.168.1.100:8001

# Output:
# ✅ Registration successful!
#    Credentials saved to ~/.olav/credentials
```

#### Step 6: Verify & Use (on Client Host)

```bash
# Test connection
uv run olav doctor

# Run queries (token auto-loaded from ~/.olav/credentials)
uv run olav query "show version"
uv run olav -q "查询 R1 BGP 状态"
```

### Security Best Practices

#### ❌ What NOT to Copy

```bash
# DO NOT copy these to client hosts:
.env                    # Contains server secrets (LLM API Key, DB passwords)
config/                 # Server configuration directory
data/                   # Server data directory
docker-compose.yml      # Server infrastructure definition
src/olav/server/        # Server-side code
```

#### ✅ What to Copy

```bash
# Only copy these to client hosts:
cli.py                  # CLI entry point
src/olav/cli/           # CLI code only
pyproject.toml          # For dependency installation
# That's it!
```

#### File Size Comparison

| Deployment Type | Size | Security Risk | Maintenance |
|----------------|------|---------------|-------------|
| **Full project copy** | ~500 MB | 🔴 High (.env leaks) | 🔴 Complex |
| **CLI-only copy** | ~10 MB | 🟢 Low | 🟢 Simple |
| **PyPI install** (future) | ~5 MB | 🟢 Low | 🟢 Automatic |

### Multi-Client Scenario

```
┌──────────────────────────────────────────────────────────────┐
│                    Server Host (192.168.1.100)                │
│                                                               │
│  ┌────────────────────────────────────────────────┐          │
│  │  OLAV Server (Docker)                          │          │
│  │  - Master Token: abc123xyz789...               │          │
│  │  - AUTH_DISABLED=false                         │          │
│  │  - Port 8001                                   │          │
│  └────────────────────────────────────────────────┘          │
└──────────────────────────────────────────────────────────────┘
                            │
                            │ HTTP/SSE (Bearer Token)
          ┌─────────────────┼─────────────────┐
          │                 │                 │
          ▼                 ▼                 ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│  Client 1        │ │  Client 2        │ │  Client 3        │
│  (Alice's Laptop)│ │  (Bob's Desktop) │ │  (CI/CD Server)  │
├──────────────────┤ ├──────────────────┤ ├──────────────────┤
│ ~/.olav/         │ │ ~/.olav/         │ │ ~/.olav/         │
│   credentials    │ │   credentials    │ │   credentials    │
│   Session Token  │ │   Session Token  │ │   Session Token  │
│   (7 days)       │ │   (7 days)       │ │   (7 days)       │
│                  │ │                  │ │                  │
│ Role: operator   │ │ Role: viewer     │ │ Role: admin      │
└──────────────────┘ └──────────────────┘ └──────────────────┘
```

### Troubleshooting

#### Issue: "Connection refused"

```bash
# Check server URL
cat ~/.olav/config.toml

# Test connectivity
curl http://192.168.1.100:<OLAV_SERVER_PORT>/health

# Check firewall
# Server host: allow OLAV_SERVER_PORT
sudo ufw allow <OLAV_SERVER_PORT>  # Linux
netsh advfirewall firewall add rule name="OLAV" dir=in action=allow protocol=TCP localport=<OLAV_SERVER_PORT>  # Windows
```

#### Issue: "Invalid or expired token"

```bash
# Check token existence
cat ~/.olav/credentials

# Re-register
uv run olav register --name "my-client" --token "<master-token>" --server <url>
```

#### Issue: "Permission denied"

```bash
# Check file permissions (Unix)
ls -la ~/.olav/credentials
# Should be: -rw------- (0600)

# Fix if needed
chmod 600 ~/.olav/credentials
```

### Advanced: Automated Deployment

**Using Ansible**:

```yaml
# playbook.yml
- name: Deploy OLAV CLI to multiple hosts
  hosts: clients
  tasks:
    - name: Copy CLI package
      copy:
        src: olav-cli-package/
        dest: /opt/olav-cli/
    
    - name: Install dependencies
      shell: uv sync
      args:
        chdir: /opt/olav-cli/
    
    - name: Configure server URL
      copy:
        content: |
          [server]
          url = "http://{{ server_ip }}:8001"
        dest: ~/.olav/config.toml
    
    - name: Register client
      shell: |
        uv run olav register \
          --name "{{ inventory_hostname }}" \
          --token "{{ master_token }}" \
          --server "http://{{ server_ip }}:8001"
      args:
        chdir: /opt/olav-cli/
```

**Using Docker** (CLI as container):

```dockerfile
# Dockerfile.cli
FROM python:3.11-slim
RUN pip install uv
COPY cli.py /app/
COPY src/olav/cli /app/src/olav/cli/
COPY pyproject.toml /app/
WORKDIR /app
RUN uv sync
ENTRYPOINT ["uv", "run", "cli.py"]

# Usage:
# docker run -e OLAV_SERVER_URL=http://server:8001 \
#            -v ~/.olav:/root/.olav \
#            olav-cli query "show version"
```

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        OLAV CLI (Thin Client)                    │
│  olav register | status | query | inspect | report | session    │
└──────────────────────────────┬──────────────────────────────────┘
                               │ HTTP/SSE (Bearer Token)
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                      OLAV API Server (FastAPI)                   │
│  /auth/* | /orchestrator/stream | /inspections/* | /reports/*  │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Workflow Orchestrator                         │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐             │
│  │   Query      │ │   Device     │ │   NetBox     │             │
│  │  Diagnostic  │ │  Execution   │ │  Management  │             │
│  │  Workflow    │ │  Workflow    │ │  Workflow    │             │
│  └──────────────┘ └──────────────┘ └──────────────┘             │
└──────────────────────────────┬──────────────────────────────────┘
                               │
          ┌────────────────────┼────────────────────┐
          ▼                    ▼                    ▼
    ┌──────────┐         ┌──────────┐         ┌──────────┐
    │  SuzieQ  │         │ NETCONF/ │         │  NetBox  │
    │ Parquet  │         │  gNMI    │         │   API    │
    └──────────┘         └──────────┘         └──────────┘
```

### Core Components

| Component | Tech Stack | Purpose |
|-----------|------------|---------|
| **CLI** | Typer + Rich | Command-line interface, TUI dashboard |
| **API Server** | FastAPI + LangServe | RESTful API, SSE streaming responses |
| **Orchestrator** | LangGraph | Workflow orchestration, intent classification |
| **State Store** | PostgreSQL | Checkpointer state persistence |
| **Schema Index** | OpenSearch | SuzieQ/OpenConfig Schema indexing |
| **Cache** | Redis (optional) | Distributed cache (fallback: in-memory) |

---

## ⚙️ Configuration Reference

### Environment Variables (.env)

```bash
# ============================================
# Required - LLM Configuration
# ============================================
LLM_API_KEY=sk-...                    # OpenAI API Key
LLM_PROVIDER=openai                   # openai | ollama | azure
LLM_MODEL_NAME=gpt-4-turbo            # Model name

# ============================================
# Optional - NetBox Configuration
# ============================================
NETBOX_URL=http://localhost:8000      # NetBox URL
NETBOX_TOKEN=your-token               # NetBox API Token

# ============================================
# Optional - Device Credentials
# ============================================
DEVICE_USERNAME=admin                 # SSH/NETCONF username
DEVICE_PASSWORD=password              # SSH/NETCONF password

# ============================================
# Required - OpenSearch Authentication
# ============================================
OPENSEARCH_USERNAME=admin             # Default username
OPENSEARCH_PASSWORD=OlavOS123!        # Change in production!
OPENSEARCH_VERIFY_CERTS=false         # Set true for production TLS

# ============================================
# Optional - Token Validity
# ============================================
TOKEN_MAX_AGE_HOURS=24                # Master Token (default 24 hours)
SESSION_TOKEN_MAX_AGE_HOURS=168       # Session Token (default 7 days)

# ============================================
# Optional - Infrastructure (Docker auto-configured)
# ============================================
# POSTGRES_URI=postgresql://olav:xxx@localhost:5432/olav
# OPENSEARCH_URL=http://localhost:19200
# REDIS_URL=redis://localhost:6379    # Optional: enables distributed cache
```

### Docker Compose Ports

| Service | Internal Port | External Port | Notes |
|---------|---------------|---------------|-------|
| olav-server | 8000 | 8001 | API Server |
| postgres | 5432 | 15432 | State persistence |
| opensearch | 9200 | 19200 | Schema index |
| redis | 6379 | 6379 | Optional (--profile cache) |
| netbox | 8080 | 8080 | Optional (--profile netbox) |

---

## 🔧 Development Guide

### Code Quality

```bash
# Format
uv run ruff format src/ tests/

# Lint + auto-fix
uv run ruff check src/ tests/ --fix

# Type checking
uv run mypy src/ --strict

# Run tests
uv run pytest -v

# Test coverage
uv run pytest --cov=src/olav --cov-report=html
```

### Add Dependencies

```bash
uv add langchain-openai          # Runtime dependency
uv add --dev pytest-asyncio      # Dev dependency
```

### Local API Server Startup

```bash
# Development mode (auto-reload)
uv run python -m olav.main serve --reload

# Or use LangGraph Studio
uv add langgraph-cli[inmem]
langgraph dev
# Access: https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024
```

---

## ⚙️ Environment Variables Reference

### Server Configuration (.env)

| Variable | Required | Default | Description | Example |
|----------|----------|---------|-------------|---------|
| **LLM Configuration** |
| `LLM_PROVIDER` | ✅ | - | LLM provider | `openai`, `ollama`, `azure` |
| `LLM_API_KEY` | ✅* | - | API key (* required for OpenAI/Azure) | `sk-...` |
| `LLM_MODEL_NAME` | ✅ | - | Model name | `gpt-4-turbo`, `qwen2.5:32b` |
| `LLM_BASE_URL` | ❌ | Provider default | API endpoint | `http://localhost:11434` (Ollama) |
| `LLM_TEMPERATURE` | ❌ | `0.1` | Sampling temperature | `0.0` - `2.0` |
| `EMBED_PROVIDER` | ✅ | - | Embedding provider | `openai`, `ollama` |
| `EMBED_MODEL_NAME` | ✅ | - | Embedding model | `text-embedding-3-small` |
| **Infrastructure** |
| `POSTGRES_URI` | ✅ | - | PostgreSQL connection | `postgresql://user:pass@host:5432/db` |
| `OPENSEARCH_URL` | ✅ | - | OpenSearch endpoint | `http://opensearch:9200` |
| `REDIS_URL` | ❌ | - | Redis cache (optional) | `redis://redis:6379` |
| **NetBox (SSOT)** |
| `NETBOX_URL` | ✅ | - | NetBox API URL | `https://netbox.company.com` |
| `NETBOX_TOKEN` | ✅ | - | NetBox API token | `abc123...` |
| **Authentication** |
| `AUTH_DISABLED` | ❌ | `true` | Disable authentication (dev only) | `true`, `false` |
| `OLAV_API_TOKEN` | ❌ | Auto-generated | Master Token (24h) | `abcd1234...` (32-byte base64) |
| `TOKEN_MAX_AGE_HOURS` | ❌ | `48` | Master Token validity (hours) | `24`, `48`, `168` |
| `SESSION_TOKEN_MAX_AGE_HOURS` | ❌ | `720` | Session Token validity (hours) | `168` (7 days), `720` (30 days) |
| **Device Credentials** |
| `DEVICE_USERNAME` | ✅ | - | SSH/NETCONF username | `admin`, `netconf-user` |
| `DEVICE_PASSWORD` | ✅ | - | SSH/NETCONF password | `secure_password` |
| `ENABLE_PASSWORD` | ❌ | - | Enable mode password (Cisco) | `enable_password` |
| **Execution Sandbox** |
| `NORNIR_RUNNER` | ❌ | `threaded` | Nornir runner type | `threaded`, `serial` |
| `NORNIR_NUM_WORKERS` | ❌ | `10` | Max parallel workers | `5`, `20`, `50` |
| `HITL_ENABLED` | ❌ | `true` | Human-in-the-loop approval | `true`, `false` |
| **Logging** |
| `LOG_LEVEL` | ❌ | `INFO` | Logging level | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `LOG_TO_FILE` | ❌ | `false` | Enable file logging | `true`, `false` |
| `LOG_FILE_PATH` | ❌ | `logs/olav.log` | Log file location | `/var/log/olav/server.log` |

### Client Configuration

#### CLI Environment Variables (Optional)

| Variable | Required | Default | Description | Example |
|----------|----------|---------|-------------|---------|
| `OLAV_SERVER_URL` | ❌ | `http://localhost:8001` | Server URL override | `http://127.0.0.1:18001` |
| `OLAV_SESSION_TOKEN` | ❌ | From `~/.olav/credentials` | Session Token (override) | `xyz789abc...` |
| `OLAV_CLIENT_ID` | ❌ | From `~/.olav/credentials` | Client UUID (override) | `550e8400-e29b-...` |

**Note**: CLI prioritizes token lookup in this order:
1. Environment variable (`OLAV_SESSION_TOKEN`)
2. Project `.env` file (if exists)
3. User credentials file (`~/.olav/credentials`)

#### Client Config File (~/.olav/config.toml)

```toml
[server]
url = "http://192.168.1.100:8001"   # Server URL
timeout = 300                        # Request timeout (seconds)

[logging]
level = "INFO"                       # CLI log level
file = "~/.olav/cli.log"            # Optional: log file

[display]
color = true                         # Enable colored output
tui = true                           # Enable TUI dashboard
```

### Environment File Examples

#### Development (.env for QuickTest)

```bash
# Example QuickTest .env (AUTH disabled)

# LLM (Ollama local)
LLM_PROVIDER=ollama
LLM_MODEL_NAME=qwen2.5:32b
LLM_BASE_URL=http://localhost:11434
EMBED_PROVIDER=ollama
EMBED_MODEL_NAME=qwen2.5:32b

# Infrastructure
POSTGRES_URI=postgresql://olav:OlavPG123!@postgres:5432/olav
OPENSEARCH_URL=http://opensearch:9200

# NetBox
NETBOX_URL=http://netbox:8080
NETBOX_TOKEN=0123456789abcdef0123456789abcdef01234567

# Device Credentials
DEVICE_USERNAME=admin
DEVICE_PASSWORD=admin

# Authentication DISABLED for dev
AUTH_DISABLED=true

# Commented production settings (for reference):
# OLAV_API_TOKEN=abc123xyz789...
# AUTH_DISABLED=false
# TOKEN_MAX_AGE_HOURS=48
# SESSION_TOKEN_MAX_AGE_HOURS=720
```

#### Production (.env for Production)

```bash
# Example Production .env (AUTH enabled)

# LLM (OpenAI GPT-4)
LLM_PROVIDER=openai
LLM_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxxxx
LLM_MODEL_NAME=gpt-4-turbo
EMBED_PROVIDER=openai
EMBED_MODEL_NAME=text-embedding-3-small

# Infrastructure
POSTGRES_URI=postgresql://olav_prod:StrongPassword123!@db.company.com:5432/olav_prod
OPENSEARCH_URL=https://search.company.com:9200
REDIS_URL=redis://cache.company.com:6379

# NetBox SSOT
NETBOX_URL=https://netbox.company.com
NETBOX_TOKEN=your_production_token_here

# Device Credentials (recommend using secrets manager)
DEVICE_USERNAME=netconf-automation
DEVICE_PASSWORD=${VAULT_DEVICE_PASSWORD}  # From secrets manager
ENABLE_PASSWORD=${VAULT_ENABLE_PASSWORD}

# Authentication ENABLED for production
AUTH_DISABLED=false
OLAV_API_TOKEN=xyz789abc456def...
TOKEN_MAX_AGE_HOURS=48              # Master Token: 2 days
SESSION_TOKEN_MAX_AGE_HOURS=168     # Session Token: 7 days

# Execution Settings
NORNIR_NUM_WORKERS=20
HITL_ENABLED=true

# Logging
LOG_LEVEL=WARNING
LOG_TO_FILE=true
LOG_FILE_PATH=/var/log/olav/server.log
```

### Security Recommendations

| Setting | Development | Production | Reason |
|---------|-------------|------------|--------|
| `AUTH_DISABLED` | `true` | `false` | Dev convenience vs security |
| `TOKEN_MAX_AGE_HOURS` | `168` (7 days) | `24` (1 day) | Reduce attack window |
| `SESSION_TOKEN_MAX_AGE_HOURS` | `720` (30 days) | `168` (7 days) | Balance convenience/security |
| `LOG_LEVEL` | `DEBUG` | `WARNING` | Reduce sensitive data in logs |
| `DEVICE_PASSWORD` | Plain text (local) | Secrets manager | Avoid .env exposure |
| `.env` File Permissions | `0644` (readable) | `0600` (owner only) | Protect secrets |

**Production Checklist**:
```bash
# 1. Verify .env permissions
chmod 600 .env

# 2. Use secrets manager for sensitive data
# Example: Vault, AWS Secrets Manager, Azure Key Vault
export DEVICE_PASSWORD=$(vault kv get -field=password secret/olav/devices)

# 3. Rotate Master Token regularly
# Generate a new value for OLAV_API_TOKEN, update .env, restart server, then re-register clients.
uv run python -c "import secrets; print(secrets.token_urlsafe(32))"

# 4. Audit session tokens
docker-compose exec postgres psql -U olav -d olav -c "SELECT client_name, expires_at FROM sessions;"
```

---

## 📚 Documentation Index

| Document | Description |
|----------|-------------|
| [MULTI_CLIENT_AUTH_DESIGN.md](docs/MULTI_CLIENT_AUTH_DESIGN.md) | Multi-client authentication design |
| [ARCHITECTURE_EVALUATION.md](docs/ARCHITECTURE_EVALUATION.md) | Architecture evaluation report |
| [DOCKER_DEPLOYMENT.md](docs/DOCKER_DEPLOYMENT.md) | Docker deployment guide |
| [CHECKPOINTER_SETUP.md](docs/CHECKPOINTER_SETUP.md) | PostgreSQL Checkpointer configuration |
| [API_USAGE.md](docs/API_USAGE.md) | API usage guide |

---

## ❓ FAQ

### Setup & Installation

**Q: setup.ps1 vs manual setup - which to use?**

- **Windows users**: Use `setup.ps1` (QuickTest default; Production enables auth)
- **Linux/Mac users**: Use `setup.sh` (same modes)
- **CI/CD**: Scripted Docker Compose + init commands (optional)

**Q: What's the difference between QuickTest and Production modes?**

| Aspect | QuickTest | Production |
|--------|-----------|------------|
| **LLM** | Ollama (local) | OpenAI/Azure (cloud) |
| **Authentication** | Disabled (`AUTH_DISABLED=true`) | Enabled with Master Token |
| **NetBox** | Docker Compose (bundled) | External (production instance) |
| **SuzieQ** | Mock data (CSV inventory) | Real NetBox data |
| **Use Case** | Local development, testing | Production deployment |

**Q: How long does initialization take?**

- **QuickTest**: ~5-10 minutes (Docker image pulls + Ollama model download)
- **Production**: ~3-5 minutes (assumes external services ready)
- **Init scripts**: ~2 minutes (PostgreSQL setup + OpenSearch indexing)

### Authentication

**Q: How to get the Master Token?**

```bash
# Production mode: use the value in the server host's .env
cat .env | grep '^OLAV_API_TOKEN='

# Generate a new token (then update .env and restart server)
uv run python -c "import secrets; print(secrets.token_urlsafe(32))"
```

**Q: What to do when Session Token expires?**

```bash
# Check expiration
cat ~/.olav/credentials
# If expired, re-register:
uv run olav register --name "my-laptop" --token "<master-token>"
```

**Q: Can I use the same Session Token on multiple machines?**

❌ **No** - each client host should have its own Session Token for audit trail:

```bash
# Machine 1
uv run olav register --name "alice-laptop" --token "<master-token>"

# Machine 2
uv run olav register --name "bob-desktop" --token "<master-token>"

# Each gets unique session_token + client_id
```

**Q: How to disable authentication (dev environment only)?**

```bash
# .env
AUTH_DISABLED=true

# Then restart server
docker-compose restart olav-server
```

⚠️ **Warning**: Never disable authentication in production!

**Q: How to revoke a Session Token?**

```bash
# Connect to PostgreSQL
docker-compose exec postgres psql -U olav -d olav

# List sessions
SELECT client_id, client_name, expires_at FROM sessions;

# Revoke by deleting session
DELETE FROM sessions WHERE client_name = 'compromised-laptop';
```

### Network Operations

**Q: Windows platform reports ProactorEventLoop error?**

OLAV handles this automatically. If issues persist:

```python
# Add at script beginning
import asyncio
asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
```

**Q: How to add devices to OLAV?**

OLAV uses **NetBox as Single Source of Truth** (SSOT):

```bash
# Step 1: Add device in NetBox WebUI
# http://localhost:8080/dcim/devices/add/
#   - Name: R1
#   - Device Type: Cisco CSR1000v
#   - Site: HQ
#   - Primary IPv4: 192.168.100.101

# Step 2: Tag device for OLAV monitoring
#   - Add tag: "${SUZIEQ_TAG_NAME:-suzieq}" (SuzieQ poller; set SUZIEQ_TAG_NAME in .env/setup)
#   - Add tag: "olav-managed" (Nornir execution)
#   - Optional: set SUZIEQ_AUTO_TAG_ALL=true before running scripts/netbox_ingest.py to auto-tag imported devices

# Step 3: Verify in OLAV
uv run olav query "show devices"
```

No manual inventory files needed!

**Q: How to use custom device credentials (per-device)?**

NetBox supports per-device credentials via Custom Fields:

```bash
# In NetBox: Add custom fields to Device model
#   - netconf_username (Text)
#   - netconf_password (Text, encrypted)

# OLAV will read these fields via NBInventory plugin
# Falls back to .env DEVICE_USERNAME/DEVICE_PASSWORD if not set
```

**Q: NETCONF connection fails with "SSH handshake failed"**

```bash
# Check device SSH config
ssh admin@192.168.100.101 -p 830 -s netconf

# Common issues:
# 1. NETCONF not enabled on device
#    Cisco: netconf-yang
#    Juniper: set system services netconf ssh

# 2. Wrong credentials
#    Check .env: DEVICE_USERNAME, DEVICE_PASSWORD

# 3. Firewall blocking port 830
#    Allow TCP 830 bidirectional
```

**Q: How to use CLI commands instead of NETCONF?**

```bash
# OLAV prefers NETCONF (structured data) over CLI (text parsing)
# For CLI-only devices, use Nornir TextFSM:

uv run olav query "execute CLI command 'show version' on R1"
# Workflow detects CLI requirement → uses netmiko + TextFSM
```

### Data & Storage

**Q: Where is SuzieQ data stored?**

```bash
# Parquet files location
ls -lh data/suzieq-parquet/
# Directory structure:
# data/suzieq-parquet/
#   ├── namespace=default/
#   │   ├── table=device/
#   │   ├── table=interfaces/
#   │   ├── table=bgp/
#   │   └── ...

# Total size: ~100MB for 100 devices (1 week data)
```

**Q: How long is historical data retained?**

```yaml
# config/suzieq-cfg.yml
retention:
  default: 30  # Days for most tables
  syslog: 7    # Days for high-volume tables
  
# Cleanup runs daily at 2 AM
```

**Q: How to backup OLAV state?**

```bash
# PostgreSQL (Checkpointer state + sessions)
docker-compose exec postgres pg_dump -U olav olav > backup_$(date +%Y%m%d).sql

# OpenSearch (schema indices)
curl -X POST "http://localhost:19200/_snapshot/backup/snapshot_1?wait_for_completion=true"

# NetBox (SSOT data)
docker-compose exec netbox python /opt/netbox/netbox/manage.py dumpdata > netbox_backup.json

# SuzieQ Parquet (historical data)
tar czf suzieq_backup.tar.gz data/suzieq-parquet/
```

### Performance & Scaling

**Q: How many devices can OLAV handle?**

| Deployment | Devices | SuzieQ Poller | Nornir Workers | Notes |
|------------|---------|---------------|----------------|-------|
| **Development** | 1-20 | 5 workers | 10 workers | Laptop (16GB RAM) |
| **Small** | 20-100 | 10 workers | 20 workers | Server (32GB RAM) |
| **Medium** | 100-500 | 20 workers | 50 workers | Multi-node SuzieQ |
| **Large** | 500+ | Distributed | 100 workers | Clustered PostgreSQL |

**Q: Queries are slow (>30 seconds)**

```bash
# Check OpenSearch index status
curl http://localhost:19200/_cat/indices?v | grep olav

# Re-index schemas if needed
docker-compose exec olav-server python -m olav.etl.init_schema

# Check SuzieQ parquet partitions
ls -lh data/suzieq-parquet/namespace=default/table=bgp/

# Optimize queries: add filters
# ❌ Slow: olav query "show all BGP sessions"
# ✅ Fast: olav query "show BGP sessions on R1"
```

**Q: High memory usage (>4GB)**

```bash
# Check Docker stats
docker stats olav-server

# Common causes:
# 1. LLM context window too large
#    Reduce in config: max_tokens=2000

# 2. Too many concurrent workflows
#    Limit: NORNIR_NUM_WORKERS=10

# 3. SuzieQ data loaded in memory
#    Increase pagination: parquet batch_size=1000
```

### Workflows & Debugging

**Q: What's the difference between Normal Mode and Expert Mode?**

| Mode | CLI Flag | Workflows | Use Case |
|------|----------|-----------|----------|
| **Normal** | Default | 3 workflows (Query/Execution/NetBox) | Single queries, device operations |
| **Expert** | `-e` or `--expert` | + DeepDiveWorkflow | Complex investigations, batch audits |

```bash
# Normal Mode
uv run olav query "show BGP status on R1"

# Expert Mode (enables DeepDiveWorkflow)
uv run olav -e "audit all edge routers for BGP misconfigurations"
# - Automatic task decomposition
# - Recursive diagnostics (max 3 levels)
# - Parallel execution (30+ devices)
# - Progress tracking + resume
```

**Q: How to enable debug logging?**

```bash
# Method 1: Environment variable
export LOG_LEVEL=DEBUG
docker-compose restart olav-server

# Method 2: .env file
echo "LOG_LEVEL=DEBUG" >> .env
docker-compose restart olav-server

# Method 3: CLI verbose mode
uv run olav -v query "test"  # -v = verbose, -vv = very verbose
```

**Q: How to view workflow execution history?**

```bash
# PostgreSQL Checkpointer stores all states
docker-compose exec postgres psql -U olav -d olav

# List recent workflows
SELECT thread_id, checkpoint_ns, created_at FROM checkpoints ORDER BY created_at DESC LIMIT 10;

# View specific workflow state (JSON)
SELECT checkpoint FROM checkpoints WHERE thread_id = 'abc-123-xyz';
```

**Q: Workflow stuck in "Waiting for approval" - how to respond?**

```bash
# Check pending HITL approvals
uv run olav status

# Output:
# Thread ID: abc-123-xyz
# Status: interrupted
# Interrupt: {"operation": "configure BGP neighbor 10.0.0.2", "device": "R1"}

# Approve (in another terminal or Web UI)
uv run olav approve abc-123-xyz --decision approve

# Or reject
uv run olav approve abc-123-xyz --decision reject --reason "Change window closed"
```

### Troubleshooting

**Q: How does 'olav status' work?**

**Architecture**: CLI calls Server API `/health/detailed` endpoint, which aggregates status from all infrastructure components.

**Benefits**:
- **True thin client**: CLI only needs server URL, no infrastructure access required
- **Consistent results**: All checks performed server-side with proper credentials
- **Cross-host compatible**: Works from any machine that can reach the server
- **No configuration needed**: CLI doesn't need NetBox URL, PostgreSQL credentials, etc.

**What's checked**:
```bash
uv run olav status

# Server checks (server-side):
# ✅ Server/Orchestrator readiness
# ✅ PostgreSQL (LangGraph checkpointer)
# ✅ OpenSearch (schema/vector index)
# ✅ Redis (optional distributed cache)
# ✅ NetBox (optional SSOT)
# ✅ LLM provider (OpenAI/Ollama)
# ✅ SuzieQ parquet data availability
```

**Troubleshooting**:
```bash
# If "Cannot connect to server" error:
1. Check server is running: docker-compose ps olav-server
2. Verify server URL: cat ~/.olav/config.toml
3. Test connectivity: curl http://127.0.0.1:<OLAV_SERVER_PORT>/health

# If component shows "Failed":
# - Check server logs: docker-compose logs olav-server
# - All checks run server-side, so errors indicate server-side issues
```

**Q: "Connection refused" when connecting to server**

```bash
# 1. Check server is running
docker-compose ps olav-server
# Should show "Up" status

# 2. Check port binding
netstat -an | grep <OLAV_SERVER_PORT>  # Linux/Mac
# Or: netstat -an | findstr <OLAV_SERVER_PORT>  # Windows

# 3. Test from server host
curl http://127.0.0.1:<OLAV_SERVER_PORT>/health
# Should return: {"status": "ok"}

# 4. Test from client host
curl http://192.168.1.100:<OLAV_SERVER_PORT>/health
# If fails, check firewall

# 5. Check server logs
docker-compose logs -f olav-server
```

**Q: "ModuleNotFoundError: No module named 'olav'"**

```bash
# Install dependencies
uv sync

# Verify installation
uv run python -c "import olav; print(olav.__version__)"
```

**Q: NetBox shows "Database connection error"**

```bash
# Check PostgreSQL container
docker-compose ps postgres

# Check NetBox migrations
docker-compose exec netbox python manage.py showmigrations

# Re-run migrations if needed
docker-compose exec netbox python manage.py migrate
```

**Q: How to reset everything and start fresh?**

```bash
# ⚠️ WARNING: This deletes ALL data (checkpoints, sessions, schemas, parquet files)

# Stop and remove containers
docker-compose down -v

# Remove data directories
rm -rf data/suzieq-parquet/*
rm -rf data/netbox-media/*

# Remove cached files
rm -rf data/cache/*

# Restart from scratch
docker-compose up -d postgres opensearch
docker-compose --profile init up olav-init
docker-compose up -d olav-server
```

### Best Practices

**Q: Production deployment checklist?**

```bash
# Security
✅ AUTH_DISABLED=false (.env)
✅ Strong OLAV_API_TOKEN (32+ bytes)
✅ .env file permissions: chmod 600
✅ Device credentials in secrets manager (not .env)
✅ HTTPS/TLS for API server (reverse proxy)

# Performance  
✅ PostgreSQL tuning (shared_buffers, max_connections)
✅ OpenSearch heap size (50% of RAM)
✅ NORNIR_NUM_WORKERS tuned for hardware

# Monitoring
✅ Prometheus metrics enabled
✅ Logs forwarded to SIEM
✅ Backup automation (PostgreSQL + OpenSearch)

# High Availability
✅ PostgreSQL replication (primary + standby)
✅ OpenSearch cluster (3+ nodes)
✅ Load balancer for API server (nginx/haproxy)
```

**Q: How to contribute to OLAV development?**

```bash
# 1. Fork repository
git clone https://github.com/your-fork/Olav.git

# 2. Create feature branch
git checkout -b feature/new-workflow

# 3. Install dev dependencies
uv sync --dev

# 4. Code quality checks
uv run ruff check src/ --fix
uv run mypy src/ --strict

# 5. Run tests
uv run pytest -v

# 6. Submit pull request
git push origin feature/new-workflow
```

---

## 📄 License

MIT License - See [LICENSE](LICENSE) for details.

---

<div align="center">

**Built with ❄️ by OLAV Team**

*NetAIChatOps - Making Network Operations Smarter*

</div>
