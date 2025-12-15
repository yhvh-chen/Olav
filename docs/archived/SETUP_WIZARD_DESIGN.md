# OLAV Setup Wizard Design Document

> **Implementation Status**: ✅ Fully Implemented (v1.0)
> - PowerShell: `scripts/setup-wizard.ps1`
> - Bash: `scripts/setup-wizard.sh`

## Overview

Provides PowerShell (Windows) and Bash (Linux/macOS) configuration wizards to guide users through OLAV initialization.

**Design Principles**:
- Interactive Q&A with friendly user experience
- Input validation and immediate testing (LLM hello test)
- Auto-generate `.env` file and necessary configurations
- All services use default ports
- **No built-in model names, user must specify**
- **NetBox is required SSOT, no direct CSV inventory support**
- **Two deployment modes: Quick Test vs Production**

## Quick Start

```powershell
# Windows (PowerShell)
.\scripts\setup-wizard.ps1                    # Interactive mode selection
.\scripts\setup-wizard.ps1 -Mode QuickTest    # Quick Test mode (5 steps)
.\scripts\setup-wizard.ps1 -Mode Production   # Production mode (8 steps)
```

```bash
# Linux/macOS (Bash)
./scripts/setup-wizard.sh                     # Interactive mode selection
./scripts/setup-wizard.sh --quick             # Quick Test mode (5 steps)
./scripts/setup-wizard.sh --production        # Production mode (8 steps)
```

## Deployment Modes

### Quick Test Mode
- **Target**: Developers, evaluators, quick demos
- **Containers**: 4 (minimal stack: OpenSearch, PostgreSQL, NetBox, NetBox-Redis)
- **Configuration**: All defaults, no OpenSearch authentication
- **User input**: LLM API Key + Model name + optional CSV import
- **Time to start**: ~3 minutes

### Production Mode
- **Target**: Production deployment, multi-user environments
- **Containers**: 4+ (can use external NetBox)
- **Configuration**: Custom credentials, OpenSearch authentication enabled
- **User input**: Full configuration wizard (8 steps)
- **Time to start**: ~10 minutes

### Mode Comparison

| Aspect | Quick Test | Production |
|--------|------------|------------|
| OpenSearch Auth | ❌ Disabled | ✅ Enabled |
| PostgreSQL Password | `olav` (default) | Custom |
| NetBox | Auto-created | Existing or new |
| Device Credentials | `admin/admin` | Custom |
| CSV Device Import | ✅ Optional | ✅ Optional |
| Port Conflict Check | ✅ Automatic | ✅ Automatic |
| Schema Initialization | ✅ Automatic | ✅ Automatic |
| Steps | 4 | 8 |

## Core Design Decisions

### NetBox as Single Source of Truth

OLAV uses **NetBox as Single Source of Truth (SSOT)** for device inventory.

- **Quick Test Mode**: Auto-create local NetBox Docker instance with defaults
- **Production Mode**: Choose between existing NetBox or new local instance

### Core Services (Both Modes)

The following 4 services are **required** in both modes:

| Service | Purpose | Container | Default Port |
|---------|---------|-----------|-------------|
| OpenSearch | Schema index, vector store | olav-opensearch | 9200 |
| PostgreSQL | LangGraph checkpointer | olav-postgres | 5432 |
| NetBox | Device inventory SSOT | olav-netbox | 8080 |
| NetBox Redis | NetBox cache/queue | olav-netbox-redis | 6379 (internal) |

**Optional Services** (can be enabled later):

| Service | Purpose | Container | Default Port |
|---------|---------|-----------|-------------|
| SuzieQ | Network observability GUI | olav-suzieq | 8501 |
| SuzieQ Poller | Device polling | olav-suzieq-poller | - |
| Fluent-Bit | Syslog collection | olav-fluent-bit | 514 |
| OLAV API Server | REST API | olav-server | 8000 |

**Note**: OLAV CLI can run directly without olav-server container.

### Port Availability Check

Windows has many reserved ports. The wizard automatically checks port availability before starting services:

```
Ports to check:
  - OpenSearch: 9200 (often conflicts with Elasticsearch)
  - PostgreSQL: 5432 (may conflict with existing PostgreSQL)
  - NetBox: 8080 (common web server port)
  - OLAV API: 8000 (if starting API server)

Windows-specific issues:
  - Hyper-V dynamic port range: 49152-65535 (may block some ports)
  - WSL2 may occupy ports unexpectedly
  - IIS default port 80/443

Detection methods:
  - Windows: Test-NetConnection -ComputerName localhost -Port <port>
  - Windows: netstat -ano | findstr :<port>
  - Linux/macOS: ss -tuln | grep :<port>
```

If a port is occupied, the wizard offers:
1. Use alternative port (e.g., 9201 instead of 9200)
2. Stop the conflicting process
3. Skip (if service is already running externally)

### Model Names by User

No default model names because:
- Models update frequently, defaults become outdated
- Different users have different model access
- Azure/Ollama deployment names are user-defined

## Configuration Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    OLAV Setup Wizard                            │
├─────────────────────────────────────────────────────────────────┤
│  0. Deployment Mode Selection                                   │
│     ├── [1] Quick Test - Minimal config, defaults everywhere   │
│     └── [2] Production - Full configuration wizard              │
│                                                                  │
│  ══════════════════════════════════════════════════════════════ │
│  QUICK TEST MODE (Steps 1-3 only)                               │
│  ══════════════════════════════════════════════════════════════ │
│                                                                  │
│  1. LLM Configuration (Required)                                │
│     ├── Provider: OpenAI/OpenAI-Compatible/Azure/Anthropic/... │
│     ├── API Key (except Ollama)                                 │
│     ├── Model name (user input, no default)                     │
│     └── Hello test validation                                   │
│                                                                  │
│  2. Embedding Configuration                                     │
│     ├── Provider: OpenAI/Google/Ollama (reuse LLM if OpenAI)   │
│     └── Model name (user input)                                 │
│                                                                  │
│  3. Port Check & Start Services                                 │
│     ├── Check port availability (9200, 5432, 8080)              │
│     ├── Offer alternative ports if conflict                     │
│     ├── Generate .env with defaults                             │
│     └── Start docker-compose (4 core containers)               │
│                                                                  │
│  4. Schema Init & Device Import                                 │
│     ├── Initialize PostgreSQL tables                            │
│     ├── Create OpenSearch indexes                               │
│     ├── Optional: Import devices from CSV                       │
│     └── Display access info                                     │
│                                                                  │
│  ══════════════════════════════════════════════════════════════ │
│  PRODUCTION MODE (Full wizard)                                  │
│  ══════════════════════════════════════════════════════════════ │
│                                                                  │
│  1. NetBox Configuration (SSOT)                                 │
│     ├── [1] Connect to existing NetBox → URL + Token → Validate│
│     └── [2] Create new local NetBox instance (Docker)          │
│           ├── Start docker-compose (NetBox stack)               │
│           ├── Wait for service ready                            │
│           ├── Create API Token                                  │
│           └── Optional: Import CSV device data                  │
│                                                                  │
│  2. LLM Configuration                                           │
│     ├── Provider: OpenAI/OpenAI-Compatible/Azure/Anthropic/... │
│     ├── API Key (except Ollama)                                 │
│     ├── Model name (user input, no default)                     │
│     ├── Endpoint (Azure/Ollama/OpenAI-Compatible)               │
│     └── Hello test validation                                   │
│                                                                  │
│  3. Embedding Configuration                                     │
│     ├── Provider: OpenAI/OpenAI-Compatible/Google/Ollama        │
│     ├── API Key (reuse LLM key or separate)                     │
│     └── Model name (user input, no default)                     │
│                                                                  │
│  4. Device Credentials                                          │
│     ├── SSH Username [default: admin]                           │
│     ├── SSH Password [default: admin]                           │
│     └── Enable Password (optional)                              │
│                                                                  │
│  5. Infrastructure Credentials & Port Detection                 │
│     ├── PostgreSQL: user/password [default: olav/OlavPG123!]   │
│     ├── OpenSearch: user/password [default: admin/OlavOS123!]  │
│     ├── Check ports: 5432/9200/8080/8000                        │
│     └── Provide alternative port options if conflict           │
│                                                                  │
│  6. Schema Initialization                                       │
│     ├── Initialize PostgreSQL tables (LangGraph checkpointer)  │
│     ├── Create OpenSearch indexes (suzieq-schema, olav-docs)   │
│     └── Index OpenConfig YANG schemas                           │
│                                                                  │
│  7. OLAV Token Generation & Auto-Registration                  │
│     ├── Generate API Token                                      │
│     └── Auto-save to ~/.olav/credentials                        │
│                                                                  │
│  8. Configuration Confirmation & Completion                     │
│     ├── Display configuration summary                           │
│     ├── Generate .env                                           │
│     ├── Generate ~/.olav/credentials                            │
│     └── Start services and verify health                        │
└─────────────────────────────────────────────────────────────────┘
```

## Step 0: Deployment Mode Selection

```
========================================
       OLAV Setup Wizard v1.0
========================================

Select deployment mode:

  [1] Quick Test
      - Minimal configuration (only LLM API Key required)
      - All infrastructure uses default credentials
      - OpenSearch security disabled
      - New local NetBox instance (auto-created)
      - Best for: Evaluation, development, demos

  [2] Production
      - Full configuration wizard
      - Custom credentials for all services
      - OpenSearch security enabled
      - Option to use existing NetBox
      - Best for: Production, multi-user environments

Choice [1/2]: 
```

---

## Quick Test Mode

### Quick Test: Step 1 - LLM Configuration

```
========================================
  Quick Test Mode - Minimal Setup
========================================

Infrastructure uses default credentials:
  - PostgreSQL: olav / olav
  - OpenSearch: security disabled (no auth)
  - NetBox: admin / admin (auto-created)

[Step 1/5] LLM Configuration

Select LLM Provider:
  [1] OpenAI
  [2] OpenAI Compatible (custom endpoint)
  [3] Azure OpenAI
  [4] Anthropic
  [5] Google AI
  [6] Ollama (local deployment)

Choice [1-6]: 1

Enter OpenAI API Key: sk-••••••••
Enter model name (e.g. gpt-4o, gpt-4-turbo): gpt-4o

Testing LLM connection...
✅ LLM Hello test successful
```

### Quick Test: Step 2 - Embedding Configuration

```
[Step 2/5] Embedding Configuration

Select Embedding Provider:
  [1] OpenAI (same API Key as LLM)
  [2] OpenAI (different API Key)
  [3] Azure OpenAI
  [4] Ollama (local deployment)

Choice [1-4]: 1

Enter Embedding model name [text-embedding-3-small]: text-embedding-3-small

✅ Embedding configuration complete
```

**If user selects [2] OpenAI (different API Key):**

```
Enter OpenAI API Key for embeddings: sk-••••••••
Enter Embedding model name [text-embedding-3-small]: text-embedding-3-small

✅ Embedding configuration complete
```

### Quick Test: Step 3 - Device Credentials

```
[Step 3/5] Device Credentials (for SSH/NETCONF access)

Enter device username [admin]: admin
Enter device password: ••••••••
Enter enable password (press Enter if same as device password): ••••••••

✅ Device credentials configured
```

### Quick Test: Step 4 - Port Check & Start Services

```
[Step 4/5] Port Availability Check

Checking required ports...

Port status:
  - OpenSearch (9200): ✅ Available
  - PostgreSQL (5432): ✅ Available
  - NetBox (8080): ⚠️ In use (Process: java.exe PID 12345)

⚠️ Port 8080 is in use!

Select action for NetBox:
  [1] Use alternative port
  [2] Stop the process (PID 12345)
  [3] Skip (I'll fix it manually)

Choice [1/2/3]: 1
Enter alternative port for NetBox [8081]: 8081
✅ NetBox will use port 8081

Starting Docker containers...
  - olav-opensearch ✅ (security disabled)
  - olav-postgres ✅
  - olav-netbox ✅ (port 8081)
  - olav-netbox-redis ✅

Waiting for services to be healthy... (approx. 60-90 seconds)
✅ All core services are ready
```

### Quick Test: Step 5 - Schema Init & Device Import

```
[Step 5/5] Initialization

Initializing schemas...
  - PostgreSQL tables (LangGraph checkpointer) ✅
  - OpenSearch indexes ✅
  - SuzieQ schema index ✅

Import devices from CSV? [y/N]: y
Enter CSV file path [config/inventory.csv]: config/inventory.csv

Validating CSV format...
✅ CSV format valid
   - Device count: 15
   - Platforms: cisco_iosxe(8), cisco_iosxr(4), arista_eos(3)

Importing devices to NetBox...
  - Creating sites... ✅
  - Creating device roles... ✅
  - Creating device types... ✅
  - Creating devices... ✅ (15/15)
  - Adding olav-managed tag... ✅

✅ Device import complete

========================================
        🎉 Quick Test Ready!
========================================

Access:
  - OLAV CLI:    python cli.py
  - NetBox:      http://localhost:8081 (admin/admin)

Imported devices: 15
Default credentials: See .env (NOT for production!)

Next: Run 'python cli.py' to start chatting with OLAV
```

### Quick Test: Default Configuration

The following `.env` is generated for Quick Test mode:

```bash
# ============================================
# OLAV Quick Test Configuration
# Generated by Setup Wizard (Quick Test Mode)
# ⚠️ NOT FOR PRODUCTION USE
# ============================================

# Deployment Mode
OLAV_MODE=quicktest

# LLM Configuration (user-provided)
LLM_PROVIDER=openai
LLM_API_KEY=sk-xxxxxxxx
LLM_MODEL_NAME=gpt-4o

# Embedding Configuration (user-selected)
EMBEDDING_PROVIDER=openai
EMBEDDING_API_KEY=${LLM_API_KEY}  # Same as LLM, or user-provided if different
EMBEDDING_MODEL_NAME=text-embedding-3-small

# Device Credentials (user-provided)
DEVICE_USERNAME=admin
DEVICE_PASSWORD=xxxxxxxx
DEVICE_ENABLE_PASSWORD=xxxxxxxx  # Optional, defaults to DEVICE_PASSWORD

# NetBox (auto-created local instance)
NETBOX_URL=http://netbox:8080
NETBOX_TOKEN=0123456789abcdef0123456789abcdef01234567
NETBOX_SUPERUSER_NAME=admin
NETBOX_SUPERUSER_EMAIL=admin@olav.local
NETBOX_SUPERUSER_PASSWORD=admin
NETBOX_SECRET_KEY=quicktest-secret-key-not-for-production-use-1234567890

# PostgreSQL (defaults)
POSTGRES_USER=olav
POSTGRES_PASSWORD=olav
POSTGRES_DB=olav

# OpenSearch (security DISABLED for quick test)
OPENSEARCH_SECURITY_DISABLED=true
# No username/password needed when security is disabled

# Port Configuration (auto-detected, may be modified if conflicts found)
OPENSEARCH_PORT=9200
POSTGRES_PORT=5432
NETBOX_PORT=8080

# Core services only (SuzieQ, Fluent-Bit are optional)
# Enable with: docker-compose --profile observability up -d
```

---

## Production Mode

### Step 1: NetBox Configuration (Production Only)

**Note**: This step only appears in Production mode. Quick Test mode auto-creates a local NetBox instance.

### Option A: Connect to Existing NetBox

```
[Step 1/8] NetBox Configuration (Device Inventory SSOT)

Select NetBox configuration method:
  [1] Connect to existing NetBox instance
  [2] Create new local NetBox instance (Docker)

Choice [1/2]: 1

Enter NetBox URL: https://netbox.example.com
Enter NetBox API Token: ••••••••

Validating NetBox connection...
✅ NetBox connection successful
   - API Version: 3.7.0
   - Device count: 42
   - Site count: 3
```

### Option B: Create New Local NetBox Instance

NetBox Docker supports automatic admin account and API Token creation via environment variables:

- `SUPERUSER_NAME` - Admin username
- `SUPERUSER_EMAIL` - Admin email
- `SUPERUSER_PASSWORD` - Admin password
- `SUPERUSER_API_TOKEN` - API Token (40 characters)

```
Choice [1/2]: 2

Creating local NetBox Docker instance...

Enter NetBox admin username [admin]: admin
Enter NetBox admin email [admin@olav.local]: 
Enter NetBox admin password: ••••••••

Generating API Token...
Generating docker-compose.override.yml...

Starting NetBox containers...
  - netbox-postgres ✅
  - netbox-redis ✅
  - netbox ✅ (main service)
  - netbox-worker ✅ (background tasks)
  - netbox-housekeeping ✅

Waiting for NetBox to be ready... (approx. 60-90 seconds)
✅ NetBox service is ready

✅ Admin account created automatically (via environment variables)
✅ API Token generated automatically

Import device data? [y/n]: y
Enter CSV file path: config/inventory.csv

Validating CSV format...
✅ CSV format validation passed
   - Device count: 15
   - Platform distribution: cisco_iosxe(8), cisco_iosxr(4), arista_eos(3)

Importing devices to NetBox...
✅ Device import complete (15/15)

NetBox configuration complete:
   - URL: http://localhost:8080
   - Admin interface: http://localhost:8080/admin
   - Username: admin
   - API Token: saved to .env
```

**Note**: NetBox Docker automatically creates superuser and token on first startup via `docker-entrypoint.sh`, no manual creation required.

### CSV Import Format

CSV files are used to import devices into NetBox, not directly as OLAV inventory:

```csv
hostname,host,platform,site,role,tags
R1,192.168.1.1,cisco_iosxe,HQ,router,olav-managed
R2,192.168.1.2,cisco_iosxr,HQ,router,olav-managed
SW1,192.168.1.10,cisco_nxos,HQ,switch,olav-managed
```

**Required columns**: `hostname`, `host`, `platform`
**Optional columns**: `site`, `role`, `tags`, `rack`, `position`

The import script will:
1. Automatically create missing Sites
2. Automatically create missing Device Roles
3. Automatically create missing Device Types (based on platform)
4. Add `olav-managed` tag to all imported devices

## Step 2: LLM Configuration (Production)

### Provider Selection

```
[Step 2/8] LLM Configuration

Select LLM Provider:
  [1] OpenAI
  [2] OpenAI Compatible (custom endpoint)
  [3] Azure OpenAI
  [4] Anthropic
  [5] Google AI
  [6] Ollama (local deployment)

Choice [1-6]: 
```

### OpenAI Configuration

```
Choice [1-6]: 1

Enter OpenAI API Key: sk-••••••••
Enter model name (e.g. gpt-4o, gpt-4-turbo): gpt-4o

Testing LLM connection...
✅ LLM Hello test successful
   - Model: gpt-4o
   - Response: "Hello! I'm ready to assist..."
```

### OpenAI Compatible Configuration

For third-party services compatible with OpenAI API (e.g., DeepSeek, Moonshot, SiliconFlow, vLLM, etc.):

```
Choice [1-6]: 2

Enter API Base URL (e.g. https://api.deepseek.com/v1): https://api.deepseek.com/v1
Enter API Key: sk-••••••••
Enter model name (e.g. deepseek-chat, deepseek-coder): deepseek-chat

Testing LLM connection...
✅ LLM Hello test successful
   - Endpoint: https://api.deepseek.com/v1
   - Model: deepseek-chat
```

### Azure OpenAI Configuration

```
Choice [1-6]: 3

Enter Azure OpenAI Endpoint: https://your-resource.openai.azure.com
Enter Azure API Key: ••••••••
Enter Deployment name: 
Enter API version (e.g. 2024-02-15-preview): 

Testing LLM connection...
✅ LLM Hello test successful
```

### Anthropic Configuration

```
Choice [1-6]: 4

Enter Anthropic API Key: sk-ant-••••••••
Enter model name (e.g. claude-3-5-sonnet-20241022): 

Testing LLM connection...
✅ LLM Hello test successful
```

### Google AI Configuration

```
Choice [1-6]: 5

Enter Google AI API Key: ••••••••
Enter model name (e.g. gemini-1.5-pro): 

Testing LLM connection...
✅ LLM Hello test successful
```

### Ollama Configuration

```
Choice [1-6]: 6

Enter Ollama Endpoint [http://localhost:11434]: 
Enter model name (e.g. qwen2.5:32b, llama3.2): 

Testing Ollama connection...
✅ Ollama Hello test successful
   - Model loaded
```

**Note**: Ollama does not require an API Key

## Step 3: Embedding Configuration (Production)

```
[Step 3/8] Embedding Configuration

Select Embedding Provider:
  [1] OpenAI
  [2] OpenAI Compatible (custom endpoint)
  [3] Google
  [4] Ollama

Choice [1-4]: 1
```

### OpenAI Embedding

```
Choice [1-4]: 1

Use the same API Key as LLM? [Y/n]: y
Enter Embedding model name (e.g. text-embedding-3-small, text-embedding-3-large): 

✅ Embedding configuration complete
```

### OpenAI Compatible Embedding

```
Choice [1-4]: 2

Use the same endpoint as LLM? [Y/n]: y
Enter Embedding model name (e.g. text-embedding-v1): 

✅ Embedding configuration complete
```

### Google Embedding

```
Choice [1-4]: 3

Enter Google API Key: ••••••••
Enter model name (e.g. models/embedding-001): 

✅ Embedding configuration complete
```

### Ollama Embedding

```
Choice [1-4]: 4

Use the same Ollama Endpoint as LLM? [Y/n]: y
Enter Embedding model name (e.g. nomic-embed-text, mxbai-embed-large): 

✅ Embedding configuration complete
```

## Step 4: Device Credentials (Production)

```
[Step 4/8] Device Credentials

Enter device SSH username [admin]: 
Enter device SSH password [admin]: 
Enter device Enable password (optional, press Enter to skip): 

✅ Device credentials configured
   - Username: admin
   - Password: ********
   - Enable: [configured]
```

**Default values**:
- SSH Username: `admin`
- SSH Password: `admin`

Users can press Enter to accept defaults.

## Step 5: Infrastructure Credentials & Port Detection (Production)

### Database Credentials

```
[Step 5/8] Infrastructure Configuration

=== PostgreSQL Configuration ===
Enter PostgreSQL username [olav]: 
Enter PostgreSQL password [OlavPG123!]: 
Enter PostgreSQL database name [olav]: 

=== OpenSearch Configuration ===
Enter OpenSearch username [admin]: 
Enter OpenSearch password [OlavOS123!]: 

✅ Database credentials configured
```

**Default values**:
| Service | Username | Password | Database |
|---------|----------|----------|----------|
| PostgreSQL | `olav` | `OlavPG123!` | `olav` |
| OpenSearch | `admin` | `OlavOS123!` | - |

### Port Detection

```
=== Port Availability Check ===

Checking port availability...

Port status:
  - PostgreSQL (5432): ✅ Available
  - OpenSearch (9200): ✅ Available
  - Redis (6379): ✅ Available
  - NetBox (8080): ⚠️ In use (Process: docker-proxy PID 12345)
  - OLAV API (8000): ✅ Available

⚠️ Port conflict detected!

Select action:
  [1] Stop the process using the port
  [2] Use alternative port
  [3] Skip (assume service is already running)

Choice [1/2/3]: 2

Enter alternative port for NetBox: 8081
✅ NetBox will use port 8081
```

### Port Detection Logic

```
Ports to check:
  - PostgreSQL: 5432
  - OpenSearch: 9200
  - Redis: 6379
  - NetBox: 8080 (only when creating new NetBox)
  - OLAV API: 8000

Detection methods:
  - Windows: Test-NetConnection -Port / netstat -ano
  - Linux/macOS: ss -tuln / netstat -tuln / lsof -i

If port is in use:
  1. Display process info (PID, process name)
  2. Offer three options
  3. Record actual port to .env
```

## Step 6: Schema Initialization (Production)

```
[Step 6/8] Schema Initialization

Starting Docker containers...
  - olav-opensearch ✅
  - olav-postgres ✅
  - olav-netbox ✅ (or using external)
  - olav-netbox-redis ✅
  - olav-suzieq ✅
  - olav-suzieq-poller ✅
  - olav-fluent-bit ✅

Waiting for services to be healthy... (approx. 60-90 seconds)
✅ All services are ready

Initializing schemas...

=== PostgreSQL Initialization ===
  Creating LangGraph checkpointer tables...
  ✅ checkpoints table created
  ✅ checkpoint_writes table created
  ✅ checkpoint_migrations table created

=== OpenSearch Initialization ===
  Creating indexes...
  ✅ olav-docs index created
  ✅ suzieq-schema index created
  ✅ openconfig-schema index created
  ✅ olav-episodic-memory index created

=== SuzieQ Schema ETL ===
  Indexing SuzieQ Avro schemas...
  ✅ 32 tables indexed (bgp, interfaces, routes, ...)

=== OpenConfig YANG ETL ===
  Indexing OpenConfig YANG schemas...
  ✅ 156 XPaths indexed

✅ Schema initialization complete
```

### Schema Initialization Details

The initialization process runs the following:

```bash
# Equivalent CLI commands:
uv run python -m olav.etl.init_postgres      # PostgreSQL tables
uv run python -m olav.etl.init_opensearch    # OpenSearch indexes
uv run python -m olav.etl.suzieq_schema_etl  # SuzieQ schema
uv run python -m olav.etl.openconfig_etl     # OpenConfig YANG
```

## Step 7: OLAV Token Generation & Auto-Registration (Production)

```
[Step 7/8] OLAV Token Generation

Generating OLAV API Token...

✅ Token generated: olav_xxxxxxxxxxxxxxxxxxxx

Registering token to CLI...
✅ Token saved to ~/.olav/credentials

You can now use CLI without specifying --token:
  python cli.py                              # Local mode
  python cli.py --server http://server:8000  # Remote mode (auto-uses registered token)
```

### Token Auto-Registration

After wizard completion, token is automatically saved to user config directory:

- **Windows**: `%USERPROFILE%\.olav\credentials`
- **Linux/macOS**: `~/.olav/credentials`

**credentials file format** (YAML):
```yaml
# OLAV CLI Credentials - Auto-generated by Setup Wizard
default_server: http://localhost:8000
tokens:
  http://localhost:8000: olav_xxxxxxxxxxxxxxxxxxxx
```

CLI automatically reads this file, no need to specify `--token` each time.

## Step 8: Configuration Confirmation & Completion (Production)

```
[Step 8/8] Configuration Confirmation

Configuration Summary:
  ┌─────────────────────────────────────────────┐
  │ Deployment Mode: Production                 │
  ├─────────────────────────────────────────────┤
  │ NetBox                                      │
  │   URL: http://localhost:8080                │
  │   Token: xxxxxxxx...                        │
  ├─────────────────────────────────────────────┤
  │ LLM                                         │
  │   Provider: openai                          │
  │   Model: gpt-4o                             │
  ├─────────────────────────────────────────────┤
  │ Embedding                                   │
  │   Provider: openai                          │
  │   Model: text-embedding-3-small             │
  ├─────────────────────────────────────────────┤
  │ Device Credentials                          │
  │   Username: admin                           │
  │   Enable: [configured]                      │
  ├─────────────────────────────────────────────┤
  │ Infrastructure                              │
  │   PostgreSQL: olav@localhost:5432           │
  │   OpenSearch: admin@localhost:9200 (secure) │
  │   NetBox: 8081 (alternative port)           │
  │   OLAV API: 8000                            │
  ├─────────────────────────────────────────────┤
  │ Core Services                               │
  │   SuzieQ GUI: http://localhost:8501         │
  │   Fluent-Bit: UDP/TCP 514 (syslog)          │
  └─────────────────────────────────────────────┘

Confirm configuration? [Y/n]: y

All services are running and healthy.

========================================
        🎉 Production Setup Complete!
========================================

Access:
  - OLAV CLI:    python cli.py
  - OLAV API:    http://localhost:8000
  - NetBox:      http://localhost:8081
  - SuzieQ GUI:  http://localhost:8501

Configuration files generated:
  ✅ .env
  ✅ ~/.olav/credentials

Documentation: docs/DOCKER_DEPLOYMENT.md
```

---

## Generated Configuration Files

### .env File (Production Mode)

```bash
# ============================================
# OLAV Configuration - Generated by Setup Wizard
# Generated at: 2024-12-09 10:30:00
# Mode: Production
# ============================================

# Deployment Mode
OLAV_MODE=production

# NetBox Configuration (SSOT)
NETBOX_URL=https://netbox.example.com
NETBOX_TOKEN=xxxxxxxxxxxx

# LLM Configuration
LLM_PROVIDER=openai
LLM_API_KEY=sk-xxxxxxxx
LLM_MODEL_NAME=gpt-4o

# OpenAI Compatible (if selected)
# LLM_PROVIDER=openai_compatible
# OPENAI_API_BASE=https://api.deepseek.com/v1
# LLM_API_KEY=sk-xxxxxxxx
# LLM_MODEL_NAME=deepseek-chat

# Azure OpenAI (if selected)
# LLM_PROVIDER=azure
# AZURE_OPENAI_ENDPOINT=
# AZURE_OPENAI_API_KEY=
# AZURE_OPENAI_DEPLOYMENT=
# AZURE_OPENAI_API_VERSION=

# Anthropic (if selected)
# LLM_PROVIDER=anthropic
# ANTHROPIC_API_KEY=

# Google AI (if selected)
# LLM_PROVIDER=google
# GOOGLE_API_KEY=

# Ollama (if selected)
# LLM_PROVIDER=ollama
# OLLAMA_BASE_URL=http://localhost:11434

# Embedding Configuration
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL_NAME=text-embedding-3-small
# EMBEDDING_API_BASE=https://api.deepseek.com/v1  # For OpenAI Compatible

# Device Credentials
DEVICE_USERNAME=admin
DEVICE_PASSWORD=admin
DEVICE_ENABLE_PASSWORD=

# PostgreSQL Configuration
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=olav
POSTGRES_PASSWORD=OlavPG123!
POSTGRES_DB=olav

# OpenSearch Configuration (Production: security enabled)
OPENSEARCH_URL=http://localhost:9200
OPENSEARCH_USER=admin
OPENSEARCH_PASSWORD=OlavOS123!
OPENSEARCH_SECURITY_DISABLED=false

# Core Services (always enabled)
# SuzieQ, SuzieQ-Poller, Fluent-Bit are automatically started

# OLAV API
OLAV_API_PORT=8000
OLAV_API_TOKEN=olav_xxxxxxxxxxxxxxxxxxxx
```

### docker-compose.override.yml (Generated when creating new NetBox)

Based on [netbox-community/netbox-docker](https://github.com/netbox-community/netbox-docker) official configuration:

```yaml
# Generated by OLAV Setup Wizard
# Adds local NetBox instance to the stack
# Based on: https://github.com/netbox-community/netbox-docker

services:
  # NetBox main service
  netbox: &netbox
    image: docker.io/netboxcommunity/netbox:${NETBOX_VERSION:-v4.4-3.4.1}
    depends_on:
      - netbox-postgres
      - netbox-redis
      - netbox-redis-cache
    env_file: config/netbox.env
    user: "unit:root"
    ports:
      - "${NETBOX_PORT:-8080}:8080"
    healthcheck:
      test: curl -f http://localhost:8080/login/ || exit 1
      start_period: 90s
      timeout: 3s
      interval: 15s
    volumes:
      - netbox-media-files:/opt/netbox/netbox/media:rw
      - netbox-reports-files:/opt/netbox/netbox/reports:rw
      - netbox-scripts-files:/opt/netbox/netbox/scripts:rw
    networks:
      - olav-network

  # NetBox background task worker
  netbox-worker:
    <<: *netbox
    depends_on:
      netbox:
        condition: service_healthy
    command:
      - /opt/netbox/venv/bin/python
      - /opt/netbox/netbox/manage.py
      - rqworker
    healthcheck:
      test: ps -aux | grep -v grep | grep -q rqworker || exit 1
      start_period: 20s
      timeout: 3s
      interval: 15s

  # NetBox housekeeping tasks
  netbox-housekeeping:
    <<: *netbox
    depends_on:
      netbox:
        condition: service_healthy
    command:
      - /opt/netbox/venv/bin/python
      - /opt/netbox/netbox/manage.py
      - housekeeping
    healthcheck:
      test: ps -aux | grep -v grep | grep -q housekeeping || exit 1
      start_period: 20s
      timeout: 3s
      interval: 15s

  # NetBox PostgreSQL
  netbox-postgres:
    image: docker.io/postgres:16-alpine
    env_file: config/netbox-postgres.env
    volumes:
      - netbox-postgres-data:/var/lib/postgresql/data
    networks:
      - olav-network

  # NetBox Redis (primary)
  netbox-redis:
    image: docker.io/valkey/valkey:8.1-alpine
    command:
      - sh
      - -c
      - valkey-server --requirepass $$REDIS_PASSWORD
    env_file: config/netbox-redis.env
    volumes:
      - netbox-redis-data:/data
    networks:
      - olav-network

  # NetBox Redis (cache)
  netbox-redis-cache:
    image: docker.io/valkey/valkey:8.1-alpine
    command:
      - sh
      - -c
      - valkey-server --requirepass $$REDIS_PASSWORD
    env_file: config/netbox-redis-cache.env
    volumes:
      - netbox-redis-cache-data:/data
    networks:
      - olav-network

volumes:
  netbox-media-files:
  netbox-postgres-data:
  netbox-redis-data:
  netbox-redis-cache-data:
  netbox-reports-files:
  netbox-scripts-files:
```

### config/netbox.env (Auto-create user and token)

```bash
# NetBox Configuration
# Superuser auto-creation via docker-entrypoint.sh
SUPERUSER_NAME=admin
SUPERUSER_EMAIL=admin@olav.local
SUPERUSER_PASSWORD=YourSecurePassword
SUPERUSER_API_TOKEN=0123456789abcdef0123456789abcdef01234567

# Database
DB_HOST=netbox-postgres
DB_NAME=netbox
DB_USER=netbox
DB_PASSWORD=netbox

# Redis
REDIS_HOST=netbox-redis
REDIS_PASSWORD=netbox-redis-password
REDIS_CACHE_HOST=netbox-redis-cache
REDIS_CACHE_PASSWORD=netbox-redis-cache-password

# Security
SECRET_KEY=your-secret-key-here-minimum-50-characters-long
```

**Key point**: NetBox Docker's `docker-entrypoint.sh` will automatically:
1. Wait for database to be ready
2. Run database migrations
3. Create superuser (if `SUPERUSER_*` environment variables are set)
4. Create API Token (if `SUPERUSER_API_TOKEN` is set)

## Features To Implement

### Script Implementation

1. **PowerShell Version** (`scripts/setup-wizard.ps1`)
   - For Windows users
   - All prompts in English
   - Mode selection (Quick Test / Production)
   - Implement NetBox connection validation (Production only)
   - Implement LLM Hello test
   - Implement CSV import to NetBox
   - Implement schema initialization

2. **Bash Version** (`scripts/setup-wizard.sh`)
   - For Linux/macOS users
   - All prompts in English
   - Same functionality as PowerShell version

### Docker Compose Files

1. **docker-compose.yml** (Base configuration)
   - Core services: OpenSearch, PostgreSQL, NetBox, SuzieQ, Fluent-Bit
   - Quick Test profile: OpenSearch security disabled
   - Production profile: OpenSearch security enabled

2. **docker-compose.quicktest.yml** (Quick Test overrides)
   - OpenSearch: `plugins.security.disabled=true`
   - PostgreSQL: Simple default password
   - NetBox: Auto-created with defaults

### Support Modules

1. **Port Check Module** (`src/olav/utils/port_check.py`)
   - Check port availability on Windows/Linux/macOS
   - Detect conflicting processes (PID, process name)
   - Suggest alternative ports
   - Handle Windows-specific issues (Hyper-V, WSL2)

2. **Schema Initialization** (`src/olav/etl/`)
   - `init_postgres.py` - LangGraph checkpointer tables
   - `init_opensearch.py` - Create OpenSearch indexes
   - `suzieq_schema_etl.py` - Index SuzieQ Avro schemas
   - `openconfig_etl.py` - Index OpenConfig YANG schemas

3. **NetBox Import Script** (`scripts/netbox_import.py`)
   - Read CSV file
   - Create Site, Device Role, Device Type
   - Batch create Devices
   - Add olav-managed tag

4. **LLM Test Module** (`src/olav/core/llm_test.py`)
   - Simple Hello test
   - Validate API Key
   - Validate model availability

5. **Settings Update** (`config/settings.py`)
   - Add `OLAV_MODE` setting (quicktest/production)
   - Support `OPENSEARCH_SECURITY_DISABLED` flag
   - Support port configuration variables
   - Support multiple LLM Providers
   - Support multiple Embedding Providers

6. **LLM Factory** (`src/olav/core/llm.py`)
   - Support 6 LLM Providers (including OpenAI Compatible)
   - Support 4 Embedding Providers

## Usage

### Windows

```powershell
# Run setup wizard (interactive)
.\scripts\setup-wizard.ps1

# Quick Test mode (minimal prompts)
.\scripts\setup-wizard.ps1 -Mode QuickTest

# Production mode (full wizard)
.\scripts\setup-wizard.ps1 -Mode Production
```

### Linux/macOS

```bash
# Run setup wizard (interactive mode selection)
chmod +x scripts/setup-wizard.sh
./scripts/setup-wizard.sh

# Quick Test mode
./scripts/setup-wizard.sh --quick

# Production mode
./scripts/setup-wizard.sh --production
```

## Docker Compose Profiles

### Quick Test Mode (4 Core Containers)

```bash
# Start core services only (OpenSearch security disabled)
docker-compose --profile quicktest up -d

# Core containers:
# - olav-opensearch (no auth)
# - olav-postgres
# - olav-netbox
# - olav-netbox-redis
```

### Production Mode (4+ Containers)

```bash
# Start with Production profile (OpenSearch security enabled)
docker-compose --profile production up -d

# Same 4 core containers, but OpenSearch requires authentication
```

### Optional Observability Services

```bash
# Add SuzieQ and Fluent-Bit for network observability
docker-compose --profile observability up -d

# Additional containers:
# - olav-suzieq (GUI on port 8501)
# - olav-suzieq-poller
# - olav-fluent-bit (syslog on port 514)
```

## Next Steps After Setup

### Quick Test Mode

```bash
# 1. Setup wizard already started containers and initialized schemas
# 2. Start OLAV CLI immediately
python cli.py

# 3. Devices already imported from CSV (if selected during setup)
# Or add manually via NetBox UI:
# Open http://localhost:8080 and add devices
```

### Production Mode

```bash
# 1. Setup wizard already completed full configuration
# 2. Verify all services
docker-compose ps

# 3. Start OLAV CLI
python cli.py

# 4. (Optional) Start OLAV API Server
docker-compose up -d olav-server
```

---

## Appendix: Code Cleanup Recommendations

Based on current code audit, the following can be cleaned up when implementing the wizard:

### 1. Prompt Manager Deprecated Methods

**File**: `src/olav/core/prompt_manager.py`

| Method | Line | Replacement | Status |
|------|------|----------|------|
| `load_agent_prompt()` | 243 | Use `load()` | To be deleted |
| `load_tool_description()` | 257 | Use `load()` | To be deleted |
| `load_workflow_prompt()` | N/A | Use `load()` | Deleted |
| `load_system_prompt()` | N/A | Use `load()` | Deleted |
| `load_raw_prompt()` | N/A | Use `load_raw()` | Deleted |

**Impact**: Only documentation references these methods, no code calls, can be directly deleted.

### 2. CLI Deprecated Parameters

**File**: `src/olav/cli/commands.py`

| Parameter | Line | Replacement | Status |
|------|------|----------|------|
| `--init` | 186 | `olav init all` | Hidden, to be deleted |
| `--init-netbox` | 195 | `olav init netbox` | Hidden, to be deleted |
| `--init-status` | 204 | `olav init status` | Hidden, to be deleted |

**File**: `src/olav/cli/client.py`

| Parameter | Line | Replacement | Status |
|------|------|----------|------|
| `local_mode` | 95-113 | `mode="local"` | To be deleted |

### 3. Debug/Test Scripts (Cleanup Candidates)

**Directory**: `scripts/`

The following scripts are one-time debug scripts and can be moved to `archive/scripts/` or deleted:

| Script | Purpose | Recommendation |
|------|------|------|
| `analyze_ebgp.py` | eBGP debug analysis | Move to archive |
| `check_bgp_config.py` | BGP config check | Move to archive |
| `debug_data.py` | PostgreSQL debug | Move to archive |
| `create_test_parquet.py` | Create test data | Keep (for testing) |
| `check_netbox.py` | NetBox connection test | Keep (for diagnostics) |
| `check_netbox_devices.py` | NetBox device check | Keep (for diagnostics) |
| `check_ospf_syslog.py` | OSPF Syslog debug | Move to archive |
| `test_*.py` (multiple) | Various test scripts | Move to tests/ or archive |

**Scripts to keep**:
- `audit_quick.py` - Code audit tool
- `audit_prompts.py` - Prompt audit tool
- `validate_prompts.py` - Prompt validation
- `generate_dev_token.py` - Dev token generation
- `netbox_ingest.py` - NetBox data import (required by wizard)
- `netbox_cleanup.py` - NetBox cleanup
- `start_api_server.py` - API server startup
- `run_e2e_tests.py` - E2E test runner
- `nornir_verify.py` - Nornir verification
- `force_sync.py` - Force sync

### 4. Documentation Cleanup

**Directory**: `docs/`

| File | Status | Recommendation |
|------|------|------|
| `QUICKSTART_LEGACY.md` | Outdated | Update or merge into README |
| `README_LEGACY.md` | Outdated | Move to archive |
| `CONFIG_REFACTOR_PLAN.md` | Completed | Move to archive |
| `REFACTOR_V2_MODES_ISOLATION.md` | Completed | Move to archive |
| `archive/DESIGN.md` | Historical reference | Keep in archive |
| `archive/LANGCHAIN_1_10_REFACTORING_PLAN.md` | Completed | Keep in archive |

### 5. Config Directory Cleanup

**Directory**: `config/`

| File | Status | Recommendation |
|------|------|------|
| `inventory.csv` | Sample data | Keep |
| `inventory.example.csv` | Sample template | Keep |
| `command_blacklist.txt` | Deprecated | Move to archive or delete |
| `cli_blacklist.yaml` | Deprecated | Confirm and delete |

### 6. Cleanup Execution Plan

```bash
# 1. Move debug scripts to archive
mkdir -p archive/scripts
mv scripts/analyze_ebgp.py archive/scripts/
mv scripts/check_bgp_config.py archive/scripts/
mv scripts/debug_data.py archive/scripts/
mv scripts/check_ospf_syslog.py archive/scripts/

# 2. Move completed design docs to archive
mv docs/CONFIG_REFACTOR_PLAN.md docs/archive/
mv docs/REFACTOR_V2_MODES_ISOLATION.md docs/archive/
mv docs/README_LEGACY.md docs/archive/

# 3. Delete deprecated prompt_manager methods (manual edit required)
# See src/olav/core/prompt_manager.py lines 243-300

# 4. Delete deprecated CLI parameters (manual edit required)
# See src/olav/cli/commands.py lines 181-210
# See src/olav/cli/client.py lines 95-113

# 5. Run tests to ensure no impact
uv run pytest -q
```

---

## Appendix: Design Completeness Analysis

### Current Manual Startup Flow vs Wizard Design

#### Current Manual Flow (README.md)

```
Step 1: Install uv + Clone repo
Step 2: uv sync --dev
Step 3: cp .env.example .env (manual edit required)
Step 4: docker-compose up -d [profile options]
Step 5: uv run olav init all
Step 6: uv run olav register --token <from-logs>
Step 7: uv run olav
```

**Pain Points**:
1. User must manually edit `.env` - many variables, easy to misconfigure
2. No validation until services fail
3. Port conflicts discovered at runtime
4. No guidance on model selection
5. Token retrieval from Docker logs is cumbersome
6. 7+ manual steps with potential for error

#### Wizard Design (Quick Test Mode)

```
Step 0: Select deployment mode
Step 1: LLM Provider + API Key + Model → Hello test
Step 2: Embedding Provider + API Key + Model
Step 3: Device Credentials (username/password/enable)
Step 4: Port check → Auto-resolve conflicts → Start containers
Step 5: Schema init → Optional CSV import → Done!
```

**Improvements**:
1. ✅ Guided input with validation at each step
2. ✅ LLM hello test before proceeding
3. ✅ Port conflict detection and resolution
4. ✅ Auto-generate `.env` with validated values
5. ✅ Single flow, no manual file editing
6. ✅ 5 steps with immediate feedback

### Coverage Analysis

| Requirement | Current Flow | Wizard Design | Status |
|-------------|--------------|---------------|--------|
| LLM API Key | .env manual | Step 1 prompt | ✅ |
| LLM Model Name | .env manual | Step 1 prompt | ✅ |
| LLM Provider (6 types) | .env manual | Step 1 menu | ✅ |
| Embedding API Key | .env manual | Step 2 prompt | ✅ |
| Embedding Model | .env manual | Step 2 prompt | ✅ |
| Device Username | .env manual | Step 3 prompt | ✅ |
| Device Password | .env manual | Step 3 prompt | ✅ |
| Enable Password | ❌ Missing | Step 3 prompt | ✅ NEW |
| Port Conflict Check | ❌ None | Step 4 auto | ✅ NEW |
| PostgreSQL Creds | .env manual | Defaults/Step 5 | ✅ |
| OpenSearch Creds | .env manual | Disabled/Step 5 | ✅ |
| NetBox Setup | docker-compose | Auto/Step 1 | ✅ |
| NetBox API Token | .env manual | Auto-created | ✅ |
| Schema Init | olav init all | Auto Step 5 | ✅ |
| CSV Import | olav init netbox | Optional Step 5 | ✅ |
| Hello Test | ❌ None | Step 1 required | ✅ NEW |

### Gap Analysis

#### Covered by Wizard ✅

| Item | Quick Test | Production |
|------|------------|------------|
| LLM Configuration (6 providers) | ✅ | ✅ |
| Embedding Configuration (4 providers) | ✅ | ✅ |
| Device Credentials + Enable Password | ✅ | ✅ |
| Port Conflict Detection (Windows/Linux) | ✅ | ✅ |
| Schema Initialization | ✅ | ✅ |
| CSV Device Import | ✅ | ✅ |
| NetBox Auto-setup | ✅ | ✅ |
| .env Auto-generation | ✅ | ✅ |
| LLM Hello Test | ✅ | ✅ |

#### Potential Gaps to Consider 🔍

| Item | Current Status | Recommendation |
|------|----------------|----------------|
| **JWT Secret Key** | Default in Quick Test | OK (dev only) |
| **SSL/TLS Setup** | Not covered | Add to Production mode later |
| **Proxy Configuration** | Not covered | Add HTTP_PROXY/HTTPS_PROXY option |
| **Multi-user Setup** | Implicit in Production | Document clearly |
| **Backup/Restore** | Not covered | Separate runbook |
| **Upgrade Path** | Not covered | Separate documentation |

### Recommended Additions

Based on analysis, the wizard design is **comprehensive** for initial setup. Consider adding:

1. **Proxy Configuration** (optional step for corporate environments):
   ```
   Does your network require a proxy? [y/N]: y
   Enter HTTP proxy URL: http://proxy.corp.com:8080
   Enter HTTPS proxy URL: http://proxy.corp.com:8080
   ```

2. **OLAV API Server** (optional in Quick Test):
   ```
   Start OLAV API Server? [y/N]: n
   (You can start it later with: docker-compose up -d olav-server)
   ```

3. **Health Check Summary** (at completion):
   ```
   ========================================
           System Health Check
   ========================================
   
   Service Status:
     - OpenSearch:  ✅ Healthy (http://localhost:9200)
     - PostgreSQL:  ✅ Healthy (localhost:5432)
     - NetBox:      ✅ Healthy (http://localhost:8080)
   
   LLM Status:
     - Provider:    OpenAI
     - Model:       gpt-4o
     - Hello Test:  ✅ Passed
   
   Devices:
     - Total:       15 (imported from CSV)
     - Platforms:   cisco_iosxe(8), cisco_iosxr(4), arista_eos(3)
   ```

### Conclusion

The wizard design is **complete and ready for implementation**:

- ✅ All required configuration items covered
- ✅ Quick Test mode minimizes friction (5 steps)
- ✅ Production mode provides full control (8 steps)
- ✅ Port detection addresses Windows pain point
- ✅ LLM hello test provides early validation
- ✅ Device credentials now include enable password
- ✅ Embedding supports separate API key

**Next Implementation Priority**:
1. `scripts/setup-wizard.ps1` (Windows PowerShell)
2. `scripts/setup-wizard.sh` (Linux/macOS Bash)
3. `src/olav/utils/port_check.py` (Port detection utility)
4. `scripts/netbox_import.py` (CSV → NetBox migration)

