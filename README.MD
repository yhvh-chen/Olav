# 🤖 OLAV - Enterprise Network Operations AI Assistant

**Version**: v0.8.0
**Status**: ✅ Production Ready
**Framework**: DeepAgents Native

OLAV (Operations Language-based Autonomous Vehicle) is an intelligent, **agentic** network assistant designed for production environments. It bridges the gap between **Generative AI** and **Deterministic Network Automation** (Nornir/Netmiko).

**[中文指南](README_ZH.md)** | **English Guide**

---

## 🌟 Why OLAV?

### 🧠 Agentic & Autonomous
Built on the **DeepAgents** framework, OLAV isn't just a chatbot. It is a goal-oriented agent that can:
- **Plan**: Break down complex requests ("Audit all BGP neighbors") into sub-tasks.
- **Act**: Execute multi-step workflows autonomously, using tools and checking results.
- **Reflect**: Verify its own outputs before reporting back to the user.
- **Memory**: Retain context across a troubleshooting session.

### 🔄 Claude Code Compatible
OLAV v0.8 adopts a 100% compatible file structure with **Claude Code** (`.claude/` ↔ `.olav/`).
- **Seamless Migration**: To use with Claude Code, simply copy `.olav/` to `.claude/` and rename `OLAV.md` to `CLAUDE.md`.
- **Standardized SOPs**: Use standard Markdown to define robust operational procedures that the Agent follows.

### 📊 Schema-Aware & Structured
Stop feeding raw text to LLMs.
- **TextFSM Native**: OLAV automatically runs CLI outputs through TextFSM templates, converting unstructured text streams into **Structured JSON**.
- **Token Efficient**: This schema-aware approach reduces context usage by 50%+ and improves analysis accuracy significantly by allowing the AI to query specific fields (`interface[0].status`) rather than parsing text.

### 🛡️ Enterprise Grade
- **3-Layer Knowledge Brain**: Decouples **Skills** (How), **Knowledge** (What), and **Capabilities** (Tools).
- **Human-in-the-Loop (HITL)**: Sensitive commands (`reload`, `config`) trigger mandatory approval gates—critical decisions require human validation.
- **Prompt Guard**: Automatic intent filtering blocks non-network queries, preventing prompt injection and off-topic requests.
- **Command Whitelisting & Blacklisting**: All executable commands are strictly whitelisted per platform (Cisco, Juniper, etc.), with explicit blacklist of forbidden operations (reload, reboot, erase, etc.), preventing dangerous or unintended operations.
- **Multi-Vendor**: Native support for Cisco, Huawei, Juniper, Arista, and any SSH-compatible device.

---

## 🚀 Quick Start

### 1. Installation
Prerequisites: Python 3.11+ (Required)

**Option A: Using uv (Recommended - Faster)**
```bash
# Install uv
pip install uv

# Install dependencies
uv sync

# Activate virtual environment (optional, uv run works without it)
source .venv/bin/activate  # On Linux/Mac
# or
.venv\Scripts\activate  # On Windows
```

**Option B: Using pip/virtualenv (Standard)**
```bash
# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate  # On Linux/Mac
# or
.venv\Scripts\activate  # On Windows

# Install dependencies
pip install -e ".[dev]"
```

### 2. Configuration (Environment)
Create your configuration file from the template:

```bash
cp .env.example .env
```

Edit `.env` with your settings:
```bash
# Required: LLM Configuration
LLM_PROVIDER=openai  # or 'ollama' for local models
LLM_API_KEY=your-api-key-here  # Get from https://platform.openai.com or https://openrouter.ai

# Optional: For local Ollama
OLLAMA_BASE_URL=http://localhost:11434

# Optional: Embedding provider for RAG
EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=nomic-embed-text:latest
```

### 3. Network Inventory Setup (Crucial)
OLAV uses Nornir to talk to your network. You must define your devices in `.olav/config/nornir/hosts.yaml`.
*Note: This is the only way OLAV knows which devices exist.*

1. Copy the example file:
   ```bash
   cp .olav/config/nornir/hosts.yaml.example .olav/config/nornir/hosts.yaml
   ```

2. Edit `hosts.yaml` with your actual device details. **This file is git-ignored** to protect credentials.

```yaml
# Example .olav/config/nornir/hosts.yaml
R1:  # <-- Alias used in Chat (e.g. "Check R1")
  hostname: 192.168.10.1
  platform: cisco_ios
  username: admin
  password: password123
  groups: ["core", "routers"]
```

### 4. Initialization (One-time)
Run the initialization script to set up all components automatically:

**If using uv:**
```bash
uv run python scripts/init.py
```

**If using pip/venv:**
```bash
python scripts/init.py
```

**What it does:**
- ✅ Generates `.olav/settings.json` from your `.env` values (model, temperature, etc.)
- ✅ Generates `.olav/knowledge/aliases.md` from your `hosts.yaml` device names
- ✅ Loads command whitelists into `capabilities.db`
- ✅ Creates `knowledge.db` schema for RAG search

**Additional options:**
```bash
# With uv
uv run python scripts/init.py --check           # Check initialization status
uv run python scripts/init.py --force           # Regenerate settings.json and aliases.md
uv run python scripts/init.py --reload-commands # Re-import commands after editing whitelists

# With pip/venv
python scripts/init.py --check
python scripts/init.py --force
python scripts/init.py --reload-commands
```

### 5. Launch

**Option A: Using uv**
```bash
uv run olav
```

**Option B: Using pip/venv (after activation)**
```bash
olav
# or
python -m olav
```

**Option C: Docker (For isolation or deployment)**
```bash
# Using OpenAI/Azure (recommended)
docker-compose up olav

# Using local Ollama LLM
docker-compose up

# Run interactively
docker-compose run --rm olav

# Pull latest Ollama model
docker-compose exec ollama ollama pull llama3
```

---

## 🔒 Security Features

OLAV implements a **defense-in-depth** security model to ensure safe autonomous operations in production networks.

### 1. **Prompt Guard** - Intent Filtering
Guards against prompt injection attacks and off-topic requests by validating that user queries are network-operations related.

- **Strict Mode**: Only explicit network operations are allowed (e.g., "Check BGP status")
- **Fuzzy Matching**: Intelligent classification to catch rephrasings of malicious prompts
- **Configurable**: Enable/disable via `guard.enabled` in `.olav/settings.json`

```json
{
  "guard": {
    "enabled": true,
    "strict_mode": false
  }
}
```

### 2. **Command Whitelisting** - Capability Control
All executable commands are strictly whitelisted per vendor platform. OLAV will **never** execute commands not in the whitelist.

**Whitelist Location**: `.olav/imports/commands/{platform}.txt`

Example `.olav/imports/commands/cisco_ios.txt`:
```
# Read-only commands
show version
show interfaces
show running-config
# Blocked by default:
# reload        ← NOT in whitelist, BLOCKED
# write erase   ← NOT in whitelist, BLOCKED
```

**Benefits**:
- Prevents accidental dangerous commands (reload, factory reset)
- Vendor-specific: Different allowed commands per platform
- Easily auditable: All permitted commands in one place

To add new commands: Edit the platform file and run:
```bash
uv run python scripts/init.py --reload-commands
```

### 2b. **Command Blacklist** - Forbidden Operations
In addition to whitelisting, OLAV maintains an explicit **blacklist** of dangerous commands that are **always** forbidden, regardless of whitelist status.

**Blacklist Location**: `.olav/imports/commands/blacklist.txt`

Example forbidden commands:
```
# Absolutely forbidden - no exceptions
reload
reboot
erase
format
delete filesystem
write erase
factory reset
shutdown
halt
```

**Why Both?**
- **Whitelist** = Explicit permission (positive control) - only listed commands are allowed
- **Blacklist** = Explicit prohibition (negative control) - even if somehow whitelisted, these are forbidden
- **Defense-in-depth**: Dual protection against accidental misconfigurations

### 3. **Human-in-the-Loop (HITL)** - Approval Gates
Critical operations automatically pause for human approval before execution.

**Approval Required For**:
- **Write Operations**: Any command that modifies device state (config, reload)
- **Skill Updates**: When agent learns new troubleshooting solutions or device aliases
- **Risky Diagnosis**: High-impact diagnosis operations requiring manual sign-off

**Configuration** (`.olav/settings.json`):
```json
{
  "hitl": {
    "require_approval_for_write": true,
    "require_approval_for_skill_update": true,
    "approval_timeout_seconds": 300
  }
}
```

**Example Flow**:
```
User: "Update the VLAN config on SW1"
Agent: 🔐 HOLD - This is a write operation
       Please confirm: set vlan 100 name prod-vlan [Y/n]
User: Y
Agent: ✅ Proceeding with update...
```

---

## 💻 Workflows & CLI

OLAV operates in two modes: **Natural Language** (Agentic) and **Workflows** (Deterministic).

### Agentic Chat
Describe what you want, and the Agent plans the execution using its Skills.
> "Check why OSPF is flapping on the Core Router"
> "Audit VLAN consistency between Access-01 and Dist-01"

### Workflow Commands (`/`)
For frequent tasks, use Slash Commands to trigger **Schema-Aware Workflows**. These are faster, cheaper (fewer tokens), and more reliable than free-form chat.

**Detailed Usage:**

*   **`/analyze [query]`**: Starts the MicroAnalyzer sub-agent.
    *   *Example*: `/analyze "Why is BGP peering down on Core-01?"`
*   **`/inspect [target]`**: Runs health checks (L1-L4).
    *   *Example*: `/inspect group:core` or `/inspect R1`
*   **`/backup`**: Backs up running-config for all/specific devices.
    *   *Example*: `/backup` (all) or `/backup group:access`

| Command | Description | Agentic Level |
|---------|-------------|---------------|
| `/analyze` | **Deep Diagnosis**: Starts the MicroAnalyzer sub-agent for root cause analysis. | ⭐⭐⭐ |
| `/inspect` | **Health Check**: Runs L1-L4 checks based on known schemas. | ⭐⭐ |
| `/backup` | **Config Backup**: Standardized workflow to save running-configs. | ⭐ |
| `/search` | **RAG Search**: Hybrid search across Local Knowledge (.md) and Web. | ⭐ |
| `/devices` | **Inventory**: List connected devices and their connection status. | - |
| `/skills` | **Skill Inventory**: List loaded Markdown SOPs. | - |
| `/stats` | **Token Usage**: Show cost and token consumption stats. | - |
| `/plan` | **Debug**: Show the Agent's current chain-of-thought and plan. | - |
| `/clear` | Clear screen. | - |
| `/quit` | Exit. | - |

---

## 🛠️ Advanced Features

### 1. Schema-Aware Parsing (TextFSM)
To teaching OLAV how to parse a new command:
1.  Drop the NTC-template file into `.olav/config/textfsm/`.
2.  Update the index file at `.olav/config/textfsm/index`.

OLAV will prioritize sending the `JSON` object to the LLM instead of the raw text block, enabling "Schema-Aware" reasoning.

### 2. Adding Skills (Claude Code Compatible)
Create a Markdown file in `.olav/skills/` to teach a new Standard Operating Procedure (SOP). OLAV natively reads **Claude Code** skill formats.

**Example: `.olav/skills/daily-check.md`**
```markdown
---
name: daily-check
description: Perform daily health checks on edge routers
version: 1.0
---
# Procedure
1. Execute `/inspect` workflow on group "edge".
2. Check for "High CPU" log patterns.
3. Report anomalies.
```

### 3. Adding Workflows
To expose a Skill as a Slash Command (Workflow):
1. Create the skill markdown as above.
2. Register it in `.olav/config/commands.yaml` (or simply rely on the auto-loader for search).
*Note: High-priority workflows like `/analyze` are hardcoded for performance.*

### 4. Knowledge Base (RAG) & Standard Paths
OLAV follows a **"Documents as Truth"** philosophy.

**Default File Locations:**
| Function | I/O | Path | Format |
|---|---|---|---|
| **Knowledge Base** | Input | `.olav/knowledge/` | `.md`, `.txt`, `.pdf` |
| **Reports** | Output | `.olav/reports/` | `.html` (Dashboard), `.json` |
| **Skills** | Input | `.olav/skills/` | `.md` (Claude Code format) |
| **Inventory** | Input | `.olav/config/nornir/hosts.yaml` | YAML |

**Usage:**
- Place local site docs into `knowledge/` and run `uv run python scripts/index_knowledge.py`.
- Find generated health reports (from `/inspect` or `/analyze`) in `reports/`.

### 5. Agentic Self-Learning
OLAV can learn from successful troubleshooting sessions and user interactions:

**Auto-Generated Content:**
| What | Path | Trigger |
|------|------|---------|
| **Solutions** | `.olav/knowledge/solutions/*.md` | After successful diagnosis, agent saves the case |
| **Device Aliases** | `.olav/knowledge/aliases.md` | When user clarifies device names (e.g., "Core router is R1") |

**Example - Learning Aliases:**
```
User: "Core switches are SW1 and SW2"
Agent: ✓ Learned alias "Core switches" → "SW1, SW2"
```
The agent appends to `aliases.md` and will use this knowledge in future queries.

**Example - Saving Solutions:**
After resolving a BGP flapping issue, the agent auto-saves:
```markdown
# Case: bgp-flapping-r1
> Created: 2026-01-12 (Auto-saved by OLAV)

## Problem
BGP neighbor flapping on R1...

## Root Cause
MTU mismatch on transit link...

## Solution
Adjusted MTU to 1500...
```

*Note: Solution auto-save requires `learning.autoSaveSolutions: true` in settings.json*

---

## 🏗️ Architecture

- **Runtime**: Python 3.12 + `uv`
- **Agent Framework**: DeepAgents
- **Database**: DuckDB (Vector + Relational)
- **Execution**: Nornir (Concurrency) + Netmiko (SSH)
- **Protocols**: SSH, Telnet, NETCONF

## 📄 License & Support

**MIT License** - Open Source & Enterprise Ready.
See `docs/` folder for detailed architectural documentation.
