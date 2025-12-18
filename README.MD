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

**Enterprise Network Operations ChatOps Platform**

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2+-green.svg)](https://langchain-ai.github.io/langgraph/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

</div>

---

## 🤖 What is OLAV?

OLAV is a **ChatOps tool designed for operating large-scale networks via natural language**. It empowers network engineers to manage thousands of devices—from multi-vendor routers to switches—simply by chatting.

Whether you need to "Check BGP status on all core routers" or "Diagnose packet loss on R1", OLAV translates your intent into precise, safe, and executed network commands. It orchestrates complex workflows using **LangGraph**, **SuzieQ** for observability, and **NetBox** as the Single Source of Truth.

## 🌟 Advanced Capabilities

### 🧠 Agentic RAG & Schema-Awareness
OLAV moves beyond simple RAG by implementing a **Schema-Aware Architecture**:

- **Dynamic Tool Registration**: Instead of hardcoding 120+ tools for every network table, OLAV uses **2 universal tools** that dynamically query SuzieQ and OpenConfig schemas. The LLM "learns" the schema on-the-fly to construct precise queries.
- **3-Tier Knowledge Base**:
  1. **Episodic Memory**: Recalls successful past workflows and intent-to-XPath mappings.
  2. **Schema Index**: Ground truth from YANG models and Avro schemas.
  3. **Docs Index**: Vendor manuals and RFCs.

### 🛡️ Safety & Governance
- **Human-in-the-Loop (HITL)**: "Safety First" philosophy. All write operations (NETCONF/CLI) trigger an interrupt requiring operator approval.
- **Funnel Debugging**: Automatically narrows down issues from Macro (network-wide SuzieQ analysis) to Micro (device-level NETCONF diagnostics).
- **Granular Access Control**: Implements a dual-token system (Master/Session) with role-based permissions to strictly separate administrative registration from operational execution.
- **Query Guard (Optional)**: LLM-based pre-filter that rejects non-network queries (prompt injection protection). Disabled by default, enable via `ENABLE_GUARD_MODE=true`.
- **Command Blacklist**: Enforces a hard block on dangerous commands (e.g., `reload`, `format`) defined in `config/command_blacklist.txt`, acting as a final safety net.

### 🌐 Multi-Vendor Support
- **No Vendor Lock-in**: Built on open standards (NETCONF/YANG, OpenConfig) and vendor-agnostic drivers.
- **Broad Compatibility**: Supports any device supported by **Nornir/Netmiko** (Cisco IOS/NX-OS, Juniper Junos, Arista EOS, Huawei, etc.).
- **Unified Data Model**: Normalizes heterogeneous network data into a consistent schema using SuzieQ, allowing unified queries across mixed-vendor environments.

### 🔄 Graceful Fallback Mechanism
- **Adaptive Execution**: Prioritizes structured data (OpenConfig/NETCONF) for reliability.
- **Automatic Fallback**: If NETCONF fails or is unavailable, automatically degrades to CLI screen scraping (TextFSM) without user intervention.
- **Resilient Operations**: Ensures tasks complete even on legacy devices with partial automation support.

## 💡 Key Scenarios

### 🚀 FastPath Diagnostics
- **Instant State Retrieval**: Bypasses complex reasoning for common queries (e.g., "Show interfaces on R1").
- **Low Latency**: Delivers sub-second responses by querying the SuzieQ data lake directly.

### 🕵️ Deep Fault Analysis
- **Recursive Investigation**: When a high-level issue is detected (e.g., "BGP Session Down"), OLAV automatically spawns sub-agents to investigate layers 1-3 (Interface errors → ARP/ND → Routing Table).
- **Root Cause Identification**: Correlates events across devices to pinpoint the exact source of failure.

### 🛡️ Automated Intelligent Inspection
- **Proactive Health Checks**: Runs scheduled or on-demand audits against "Golden State" definitions.
- **Log Anomaly Detection**: Analyzes syslog streams to detect silent failures or intermittent issues that don't trigger SNMP traps.
- **Compliance Verification**: Ensures configurations match the design intent in NetBox.

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (Fast Python package installer)
- Docker & Docker Compose

### Installation

1. **Clone and Setup**
   ```bash
   git clone https://github.com/yourusername/Olav.git
   cd Olav
   
   # Install dependencies
   uv sync --dev
   ```

2. **Configuration**
   ```bash
   # 1. Environment Variables
   cp .env.example .env
   # Edit .env to set your LLM API keys and NetBox credentials
   
   # 2. Inventory Setup
   cp config/inventory.example.csv config/inventory.csv
   # Edit inventory.csv to add your initial seed devices.
   # TIP: Use the 'tags' column to specify protocol preference:
   #      - 'cli': Force CLI/TextFSM (e.g., legacy devices)
   #      - 'openconfig': Prefer NETCONF/OpenConfig (default if supported)
   ```

3. **Start Infrastructure**
   ```bash
   docker-compose up -d
   ```

4. **Initialize & Run**
   ```bash
   # Windows
   .\setup.ps1
   
   # Linux/Mac
   ./setup.sh
   
   # Start CLI
   uv run olav
   ```

## 🎮 CLI Usage Guide

### Interactive Mode
Start the chat session for ad-hoc queries and operations.
```bash
uv run olav
```

### Expert Mode
For complex troubleshooting that requires recursive investigation (e.g., "Why is BGP flapping on R1?"), use Expert Mode. This enables the **DeepDiveWorkflow** which can spawn sub-agents to investigate multiple layers (L1-L3) automatically.

```bash
uv run olav -e "Diagnose intermittent packet loss on Core-Switch-01"
# OR
uv run olav --expert "Check BGP anomalies in DataCenter-A"
```

### Automated Inspection
Run declarative health checks defined in YAML configuration files.

1. **Define Inspection Profile**:
   Create or edit YAML files in `config/inspections/`.
   
   *Example `config/inspections/daily_check.yaml`:*
   ```yaml
   name: daily_check
   type: device-check
   devices:
     netbox_filter: { role: "core" }
   checks:
     - name: "BGP State"
       table: bgp
       assert: "state == 'Established'"
   ```

2. **Manage Inspections**:
   ```bash
   # List available profiles
   uv run olav inspect list
   
   # Run a specific profile
   uv run olav inspect run daily_check
   
   # Check job status
   uv run olav inspect jobs
   ```

## 🔒 Distributed Architecture & Security

OLAV is designed for enterprise scale and security:

### Server-Client Separation
- **Decoupled Design**: The heavy-lifting Core Server (LangGraph/LLM) runs centrally, while lightweight Clients (CLI) can be deployed anywhere.
- **Flexible Deployment**: Run the server in a secure enclave/VPC, and distribute clients to operations teams.

### 🔐 Zero-Trust Security Model
- **Token Separation**:
  - **Master Token**: Auto-generated on server startup, used for client registration.
  - **Session Tokens**: Unique, revocable tokens issued to each client device.
- **Role-Based Access**: `admin` (skip HITL) | `operator` (HITL required) | `viewer` (read-only).

## 🔑 Token Management

**Server Startup** (Master Token auto-generated):
```bash
docker-compose up -d
# Master Token printed in logs: docker-compose logs olav-app | grep "Master Token"

# Or set fixed token in .env for multi-worker mode:
# OLAV_API_TOKEN=<your_secure_token>
```

**Client Registration** (with role):
```bash
# Register as operator (default, HITL required for writes)
olav register -n my-laptop -t <MASTER_TOKEN> --server http://<SERVER>:<PORT>

# Register as admin (can skip HITL)
olav register -n admin-station -t <MASTER_TOKEN> --role admin --server http://<SERVER>:<PORT>

# Register as viewer (read-only)
olav register -n monitoring-client -t <MASTER_TOKEN> --role viewer --server http://<SERVER>:<PORT>

# Verify
olav status
```

**Session Management** (server-side):
```bash
uv run olav token list              # List all registered clients
uv run olav token revoke <name>     # Revoke a client's access
```

## 💻 CLI Client Deployment

OLAV supports two deployment modes: **Local CLI** (full environment) and **Remote CLI** (lightweight client).

### Local CLI (Full Environment)
Use this mode when running directly on the OLAV server or development machine with the full environment.

```bash
# Start interactive mode
uv run olav

# Single query
uv run olav -q "Check BGP status on R1"

# Expert mode (Deep Dive)
uv run olav -e "Diagnose packet loss on Core-Switch-01"
```

### Remote CLI (Lightweight Client)
For operators who need to connect to a remote OLAV server without installing the full environment.

**Installation:**
```bash
# From PyPI (when published)
pip install olav-client

# Or install from source
cd client/
uv pip install .
```

**Configuration:**

The server URL and port depend on your OLAV server deployment. Check your `.env` file for:
- `OLAV_SERVER_PORT_EXTERNAL` - the external port exposed by the server (default: `18000`)

```bash
# Set server URL via environment variable
export OLAV_SERVER_URL=http://<SERVER_IP>:${OLAV_SERVER_PORT_EXTERNAL}

# Or use config file: ~/.olav/config.toml
cat > ~/.olav/config.toml << EOF
[server]
url = "http://your-server:18000"  # Match your .env OLAV_SERVER_PORT_EXTERNAL
timeout = 300
EOF
```

**Register Client:**
```bash
# First-time registration (requires Master Token from admin)
olav register -n my-laptop -t <MASTER_TOKEN> --server http://<SERVER_IP>:<PORT>
```

**Usage:**
```bash
# Interactive chat loop
olav

# Single-shot query
olav -q "Show interfaces on R1"

# Check connectivity and autocomplete
olav status
```

### Deployment Comparison

| Feature | Local CLI (`uv run olav`) | Remote CLI (`olav-client`) |
|---------|---------------------------|---------------------------|
| Installation | Full environment + dependencies | Lightweight pip package |
| Network Access | Direct to devices | Via OLAV server API |
| Expert Mode | ✅ Supported | ✅ Supported |
| Inspection | ✅ Full access | ✅ Via server |
| Use Case | Server/Dev machine | Operator workstations |

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
