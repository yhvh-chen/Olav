# 🤖 OLAV - Enterprise Network Operations AI Assistant

**Version**: v0.8.0
**Status**: ✅ Production Ready

OLAV is an advanced AI assistant designed for network engineers. It combines the power of Large Language Models (LLMs) with enterprise-grade network automation tools to help you diagnose, configure, and monitor your network infrastructure.

**[中文指南](i18n/zh.md)** | **English Guide**

---

## 🚀 Quick Start

### 1. Installation

Prerequisites: Python 3.10+

```bash
# Install using uv (recommended for speed)
pip install uv
uv sync
```

### 2. Configuration

Create your configuration file:

```bash
cp .env.example .env
# Edit .env to add your API keys (OpenAI, Anthropic, etc.) and device credentials
```

### 3. Launch

Start the interactive CLI:

```bash
uv run olav.py
```

---

## ✨ Key Features

### 🧠 Intelligent Diagnosis
Describe network issues in natural language. OLAV analyzes the problem, formulates a plan, and investigates using connected devices.
* "Why is OSPF flapping on R1?"
* "Check for interface errors on Core-Switch-01"

### 🔍 Research & Search
Integrated web search and local knowledge base lookup to assist troubleshooting.
* `/search "cisco bgp error code 123"` - Search online documentation (DuckDuckGo)
* `/search "internal vlan policy"` - Search local knowledge base
* Automatic fallback to web search when local knowledge is insufficient.

### 🛠️ Interactive CLI
A powerful command-line interface with persistent history and auto-completion.
* `/help` - Show available commands
* `/devices` - List connected network devices
* `/skills` - View available AI capabilities (Skills)
* `/history` - View command history

### 🌐 Multi-Vendor Support
Native support for major network vendors using Nornir/Netmiko. Because it leverages standard SSH protocols, it **theoretically supports any SSH-compatible device**.
- Cisco (IOS, NX-OS)
- Huawei (VRP)
- Juniper (Junos)
- Arista (EOS)
- *Any device supported by Netmiko*

### 🎨 Customization
Customize your CLI experience.
- **Banners**: Choose from built-in banners (Snowman, DeepAgents) or create your own company banner.
- **Settings**: Configure `.olav/settings.json` to tailor the agent behavior.

---

## 📖 User Guide

### Natural Language Interaction
Just type what you need. OLAV uses "Skills" (defined in Markdown) to understand your intent and execute complex workflows.

> "Backup the running config for all access switches"
> "Audit the BGP configuration on the border routers and check for inconsistencies"

### Core Slash Commands
Quick access to system functions:

| Command | Description |
|---------|-------------|
| `/analyze` | Start a deep diagnosis session with the MicroAnalyzer sub-agent |
| `/inspect` | Perform a quick health check (L1-L4) on devices |
| `/backup` | Trigger a configuration backup workflow |
| `/search` | Search knowledge base and web for information |
| `/devices` | Show inventory and connection status |
| `/skills` | List loaded capabilities and strategies |
| `/memory` | Inspect the agent's short-term memory |
| `/clear` | Clear the terminal screen |
| `/quit` | Exit OLAV |

### Configuration Management
OLAV allows extensive customization to fit your environment.

#### 1. LLM Setup (First Run)
Edit your `.env` file to configure the AI backend:
```ini
LLM_PROVIDER=openai  # openai, azure, or ollama
LLM_API_KEY=sk-proj-...
LLM_MODEL_NAME=gpt-4-turbo
# Optional: Nornir inventory path
NORNIR_CONFIG_FILE=config/nornir_config.yaml
```

#### 2. Adding Vendor Commands and TextFSM
To support new CLI commands, add them to the whitelist files in `.olav/imports/commands/`:
- `cisco_ios.txt`
- `huawei_vrp.txt`
**Rules:**
- `show version` : Standard allow
- `!copy run start` : Requires **Human Approval (HITL)**
- `#show version` : **Temporarily Disabled**. The command is simply not loaded into the available toolset.
- **Global Blacklist**: **Security Block**. Commands in `.olav/imports/commands/blacklist.txt` are strictly blocked.
    > *Note: Blacklist overrides Whitelist. Even if `reload` is added to a whitelist, the Blacklist will still prevent its execution.*

**Custom TextFSM Parsing (Save Tokens):**
OLAV uses `ntc-templates` by default. To optimize performance and reduce LLM token usage:
1. Place custom `.teplate` files in `.olav/config/textfsm/`.
2. Map them in `.olav/config/textfsm/index` (NTC format).
Parsed Structured Data (JSON) is much cheaper for LLMs to process than raw text block.

#### 3. Knowledge Base system
OLAV follows a **"Documents as Truth"** philosophy: Answers derived from your local Knowledge Base are prioritized over general LLM training data.

- **Add Knowledge**: Drop Markdown (`.md`) files into `.olav/knowledge/`.
- **Index Knowledge**: Run the indexer to vectoring your contents:
  ```bash
  uv run python scripts/index_knowledge.py --source local --path .olav/knowledge/
  ```
- **Remove Knowledge**: Delete the file and re-run the indexer (or use `--init` to rebuild).
- Use `/search` to query this knowledge.

#### 4. Banners
Edit `config/banners.py` to change the CLI look and feel.

---

## 🏗️ Architecture Overview

OLAV is built on the **DeepAgents** framework, featuring a unique **3-Layer Knowledge Architecture**:

1.  **Skills (HOW)**: Strategies and Standard Operating Procedures (SOPs) defined in Markdown.
2.  **Knowledge (WHAT)**: Environment facts, site codes, and historical solutions.
3.  **Capabilities (CAN)**: Validated tool definitions and CLI command whitelists (Cisco/Huawei/etc).

This design ensures the AI operates within safe, predefined boundaries while maintaining the flexibility to learn new tasks.

---

## 📄 License & Support

**License**: MIT License
**Documentation**: See `docs/` folder for detailed guides.
**Feedback**: Please file an issue on GitHub for bugs or feature requests.

---

## 🔧 Advanced Customization

### 1. Extending Nornir Inventory
OLAV uses Nornir for network interactions. To add your devices manually:
1. Open `.olav/config/nornir/hosts.yaml`.
2. Add device entries following the standard Nornir SimpleInventory format:
   ```yaml
   Router01:
     hostname: 192.168.1.1
     groups: ["cisco_ios", "core"]
     data:
       site: "NewYork"
   ```
3. Alternatively, configure a dynamic inventory plugin (e.g., NetBox) in `.olav/config/nornir/config.yaml`.

### 2. Creating Custom Skills
You can teach OLAV new workflows by creating a Markdown file in `.olav/skills/`.

**Example:** `.olav/skills/my-audit.md`
```markdown
---
name: VLAN Audit
description: Check for VLAN inconsistencies across switches
version: 1.0.0
---

# VLAN Audit Procedure
1. Get checklist of required VLANs.
2. For each switch in group 'access':
    a. Run `show vlan brief`
    b. Compare against requirements.
3. Report missing VLANs.
```
OLAV will automatically load this skill and use it when you ask "Audit VLANs".

### 3. Migrating from Claude Code
If you have existing skills from Claude Code or compatible agents:
1. Copy your skill files to `.olav/skills/`.
2. Run the migration tool to normalize formats:
   ```bash
   uv run python scripts/migrate_to_claude_code.py
   ```
This ensures your skills are compatible with the OLAV engine.
