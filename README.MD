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
- **Seamless Migration**: Drop your existing Claude Code prompts and skills directly into `.olav/skills`.
- **Standardized SOPs**: Use standard Markdown to define robust operational procedures that the Agent follows.

### 📊 Schema-Aware & Structured
Stop feeding raw text to LLMs.
- **TextFSM Native**: OLAV automatically runs CLI outputs through TextFSM templates, converting unstructured text streams into **Structured JSON**.
- **Token Efficient**: This schema-aware approach reduces context usage by 50%+ and improves analysis accuracy significantly by allowing the AI to query specific fields (`interface[0].status`) rather than parsing text.

### 🛡️ Enterprise Grade
- **3-Layer Knowledge Brain**: Decouples **Skills** (How), **Knowledge** (What), and **Capabilities** (Tools).
- **Human-in-the-Loop (HITL)**: Sensitive commands (`reload`, `config`) triggers mandatory approval gates.
- **Multi-Vendor**: Native support for Cisco, Huawei, Juniper, Arista, and any SSH-compatible device.

---

## 🚀 Quick Start

### 1. Installation
Prerequisites: Python 3.10+

```bash
# Install using uv (recommended for speed)
pip install uv
uv sync
```

### 2. Configuration (Environment)
Create your configuration file from the template:

```bash
cp .env.example .env
# Edit .env to add your LLM API Key (OpenAI, DeepSeek, etc.)
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
You **MUST** run this script to index devices, load command whitelists, and build the vector database.

```bash
uv run python scripts/init_capabilities.py
```
*Output: "Successfully loaded X commands, Y devices..."*

### 5. Launch
Start the interactive Agent CLI:

```bash
uv run olav.py
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

**Migration Helper**:
Converting existing Skills to the new format? Use the included tool:
```bash
uv run python scripts/migrate_to_claude_code.py --path ./old_skills/
```

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
OLAV follows a **"Documents as Truth"** philosophy.
- Place your site docs (PDF/MD) in `.olav/knowledge/`.
- Run `uv run python scripts/index_knowledge.py` to vectorize.
- Use `/search` to retrieve this specific context during troubleshooting.

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
