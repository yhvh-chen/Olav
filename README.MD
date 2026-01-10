# 🤖 OLAV - Enterprise Network Operations AI Assistant

**Version**: 0.8.0  
**Status**: ✅ Production Ready  
**Architecture**: DeepAgents Native + Three-Layer Knowledge Architecture (Skills/Knowledge/Tools)  
**CLI**: Interactive DeepAgent CLI  
**Platform**: Compatible with Claude Code, supports Windows/Mac/Linux  

**[中文指南](i18n/zh.md)** | **English Guide**

---

## 📋 Table of Contents

- [Quick Start](#quick-start)
- [Features](#features)
- [Installation](#installation)
- [Usage Examples](#usage-examples)
- [Backup Guide](#backup-usage-guide)
- [Architecture](#architecture)
- [Technology Stack](#technology-stack)

---

## Quick Start

### 1️⃣ Environment Setup (5 minutes)

```bash
# Install dependencies (using uv - fast package manager)
uv sync --dev

# Copy environment configuration
cp .env.example .env
# Edit .env and add your device information and API keys
```

### 2️⃣ Launch Interactive CLI

```bash
# Start DeepAgent CLI
uv run python -m olav.main

# Welcome to OLAV Interactive CLI
# Type /help for available commands
```

### 3️⃣ Use Slash Commands in CLI

```
OLAV> /devices
✅ R1, R2, R3, R4, SW1, SW2 (Connected)

OLAV> Check R1 interface status
🔍 Query matched to 'quick-query' skill
...

OLAV> /inspect layer3
📊 L3 Inspection Report
...

OLAV> /skills
📚 Available Skills: device-inspection, quick-query, deep-analysis, config-backup

OLAV> /history
📜 Recent commands...

OLAV> /quit
```

### 4️⃣ Use with Claude Code

```
1. Navigate to the project directory
2. Open in Claude Code
3. OLAV CLI automatically integrates with agent
4. View available skills: `/skills`
5. Send command: "Backup role:core devices running config"
```

---

## Features

### 🎯 Four Core Capabilities

#### 1. **Device Inspection** - Comprehensive Device Health Check
- **L1 Physical Layer**: CPU/Memory/Temperature/Power/Fans
- **L2 Data Link**: VLAN/STP/LLDP/MAC Table
- **L3 Network**: Routes/OSPF/BGP/VPNv4
- **L4 Transport**: TCP/Processes/Memory/Error Counters

#### 2. **Quick Query** - Fast 1-2 Command Responses
- Immediate responses for simple queries
- Automatic command selection
- Multi-vendor support (Cisco/Huawei/Arista)

Examples:
```
"Check R1 CPU usage"
"Show interface status on SW1"
"Get BGP neighbors from R3"
```

#### 3. **Deep Analysis** - Multi-Step Complex Diagnostics
- Multi-step troubleshooting workflows
- Automatic problem localization
- Remediation suggestions

Examples:
```
"Diagnose why R1 BGP neighbors are down"
"Analyze interface error rates on core switches"
"Check network security baseline compliance"
```

#### 4. **Device Backup** - Intelligent Configuration Backup
- Flexible filtering by group/role/site
- Single or batch device backup
- Automatic file naming and timestamping
- Git version control integration

Examples:
```
"Backup all core devices running config"
"Save group:test startup configs"
"Backup role:border running-config"
```

---

### 🔧 Claude Code & Multi-Platform Support

OLAV supports **Claude Code**, **Cursor IDE**, and other agent platforms with:

- ✅ **Automated Migration Tool** - One-command conversion: `python scripts/migrate_olav_to_agent.py --platform claude`
- ✅ **Dual Format Support** - Works with both `.olav/skills/*.md` (legacy) and `skills/*/SKILL.md` (new)
- ✅ **Knowledge Management** - Search, reload, and sync with hybrid FTS + vector search
- ✅ **Compatibility Verification** - Automated checking with `verify_claude_compatibility.py`
- ✅ **Safe Migration** - Automatic backup before any changes, dry-run mode available
- ✅ **80+ Test Cases** - Comprehensive testing for reliability

**Quick Migration**:
```bash
# Test first (no changes)
python scripts/migrate_olav_to_agent.py --platform claude --dry-run

# Execute (with auto-backup)
python scripts/migrate_olav_to_agent.py --platform claude

# Verify
python scripts/verify_claude_compatibility.py .
```

**Available Tools**:
- `search-knowledge.py` - Hybrid knowledge search
- `reload-knowledge.py` - Update knowledge base
- `sync-knowledge.py` - Database synchronization
- See [AGENT_MIGRATION_GUIDE.md](AGENT_MIGRATION_GUIDE.md) for complete documentation

---

## Installation

### Prerequisites

- **Python 3.11+** (recommend 3.13)
- **uv** package manager (quick install: `pip install uv`)
- **Network devices** (Cisco IOS/XE, Huawei, Arista, etc.)
- **SSH access** to network devices

### Complete Installation Steps

```bash
# 1. Clone repository
git clone https://github.com/your-org/OLAV.git
cd OLAV

# 2. Install dependencies
uv sync --dev

# 3. Configure environment
cp .env.example .env
# Edit .env:
# - DEVICE_USERNAME=admin
# - DEVICE_PASSWORD=password
# - OPENAI_API_KEY=sk-...

# 4. Configure Nornir (network device inventory)
# Edit .olav/config/nornir/hosts.yaml
# Edit .olav/config/nornir/groups.yaml

# 5. Start interactive CLI and test
uv run python -m olav.main

# In CLI, test basic commands:
# OLAV> /devices
# OLAV> Check device connectivity
# OLAV> /quit
```

---

## Usage Examples

### Example 1: Launch CLI and Query Device

```bash
# Start interactive CLI
$ uv run python -m olav.main

# OLAV> R1 interface status
# 🔍 Query matched to 'quick-query' skill
# Executing: show ip interface brief on R1
# ...
# ✅ Task completed
#
# OLAV>
```

### Example 2: View Available Devices

```bash
# OLAV> /devices
# 📋 Connected Devices:
#   R1 (Cisco IOS) - Group: test, Role: border, Site: lab
#   R2 (Cisco IOS) - Group: test, Role: border, Site: lab
#   R3 (Cisco IOS) - Group: test, Role: core, Site: lab
#   R4 (Cisco IOS) - Group: test, Role: core, Site: lab
#   SW1 (Cisco IOS) - Group: test, Role: access, Site: lab
#   SW2 (Cisco IOS) - Group: test, Role: access, Site: lab
```

### Example 3: Perform Comprehensive Inspection

```bash
# OLAV> Inspect all lab devices with comprehensive L1-L4 check
# 🔍 Query matched to 'device-inspection' skill
# 📊 L1-L4 Inspection Report for lab group
#   ├─ Executive Summary (overall status of 6 devices)
#   ├─ L1 Physical: CPU/Memory/Temp/Power ✅
#   ├─ L2 Data Link: VLAN/STP/LLDP ✅
#   ├─ L3 Network: Routes/OSPF/BGP ✅
#   ├─ L4 Transport: TCP/Processes ✅
#   └─ Anomalies: None detected
#
# 📁 Report saved to: .olav/reports/lab-comprehensive-l1l4-20260108-143000.html
```

### Example 4: Use File References and Shell Commands

```bash
# OLAV> Analyze this config @network-config.txt against best practices
# 📄 File loaded: network-config.txt (1024 bytes)
# 🔍 Query matched to 'deep-analysis' skill
# ...

# OLAV> !ping -c 4 192.168.1.1 && Check if R1 is responding
# $ ping -c 4 192.168.1.1
# PING 192.168.1.1 (192.168.1.1) 56(84) bytes of data
# ...
# ✅ R1 is responding with 0% packet loss
```

### Example 5: Backup Device Configurations

```bash
# Single device backup
OLAV> Backup R1 running config
🔍 Query matched to 'config-backup' skill
📁 Saving R1 running configuration
✅ Saved to: .olav/data/configs/R1-running-config-20260108-120000.txt

# Backup by role
OLAV> Backup all core role devices running config
🔍 Query matched to 'config-backup' skill
📁 Found 2 core devices: R3, R4
✅ Saving R3 running configuration
✅ Saving R4 running configuration

# Backup by group
OLAV> Backup test group startup config
🔍 Query matched to 'config-backup' skill
📁 Found 6 test group devices
✅ Saving configurations (6 files)

# Backup by site
OLAV> Backup all lab devices running configs
🔍 Query matched to 'config-backup' skill
📁 Found 6 lab site devices
✅ Batch backup complete (6 files saved)
```

---

## Backup Usage Guide

### Device Filtering Options

The backup skill supports multiple filtering methods:

| Filter Type | Syntax | Example |
|------------|--------|---------|
| **Single Device** | Device name | `backup R1 running config` |
| **Multiple Devices** | Comma-separated | `backup R1,R2,R3 running config` |
| **By Role** | `role:` prefix | `backup role:core running config` |
| **By Group** | `group:` prefix | `backup group:test running config` |
| **By Site** | `site:` prefix | `backup site:lab running config` |
| **All Devices** | `all` keyword | `backup all running config` |

### Backup File Locations

All backups are automatically saved to `.olav/data/configs/` with timestamped filenames:

```
.olav/data/configs/
├── R1-running-config-20260108-120000.txt
├── R2-running-config-20260108-120000.txt
├── R3-startup-config-20260108-120000.txt
└── ...
```

### Viewing Available Devices

```bash
OLAV> /devices
📋 Available Devices (with attributes):

Device | Groups | Role | Site
-------|--------|------|------
R1     | test   | border | lab
R2     | test   | border | lab
R3     | test   | core | lab
R4     | test   | core | lab
SW1    | test   | access | lab
SW2    | test   | access | lab
```

### Git Version Control

Track configuration changes with Git:

```bash
# Initialize (one-time)
cd .olav/data
git init
git config user.name "OLAV Backup"

# After backups are saved
git add configs/
git commit -m "Backup $(date +%Y%m%d-%H%M%S)"

# View backup history
git log --oneline | head -10
```

---

## Advanced Usage

## Advanced Usage

### Three-Layer Knowledge Architecture

```
┌────────────────────────────────────────────────────────┐
│          OLAV Three-Layer Knowledge Architecture        │
├────────────────────────────────────────────────────────┤
│                                                        │
│  Layer 1: SKILLS (.olav/skills/*.md or */SKILL.md)    │
│  ├─ device-inspection    → Comprehensive L1-L4 check  │
│  ├─ quick-query          → Fast 1-2 command queries   │
│  ├─ deep-analysis        → Multi-step diagnostics     │
│  └─ config-backup        → Configuration backup       │
│     [Strategy Layer - HOW: How to execute tasks]       │
│                                                        │
│  Layer 2: KNOWLEDGE (.olav/knowledge/*.md)            │
│  ├─ aliases.md           → Device alias mapping       │
│  ├─ topology.md          → Network topology           │
│  └─ solutions/           → Solutions & patterns       │
│     [Knowledge Layer - WHAT: What are facts]          │
│                                                        │
│  Layer 3: TOOLS/CAPABILITIES                          │
│  ├─ Nornir               → SSH batch execution        │
│  ├─ search-knowledge     → Unified search tool        │
│  ├─ DuckDB              → CLI/API/NETCONF library     │
│  └─ LangChain           → LLM integration             │
│     [Capability Layer - CAN: What we can do]          │
│                                                        │
└────────────────────────────────────────────────────────┘
```

### Execution Flow

```
User Input
  ↓
┌─────────────────────────┐
│ LLM Skill Router        │
│ (Intent Recognition +   │
│  Routing)              │
└──────────┬──────────────┘
           ↓
      Select Skill
           ↓
┌──────────────────────────┐
│ Skill Execution Engine   │
│ (Parse scope +           │
│  Execute commands)       │
└──────────┬───────────────┘
           ↓
    Nornir Batch Execution
           ↓
┌──────────────────────────┐
│ Report Generation        │
│ (Jinja2 templates +      │
│  HTML output)           │
└──────────┬───────────────┘
```

---

## Architecture

### Core Technologies

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Framework** | DeepAgents | Agent orchestration and HITL |
| **LLM** | OpenAI/Claude | Intent recognition and routing |
| **CLI** | prompt-toolkit 3.0+ | Interactive command interface |
| **Network** | Nornir 3.3 | Multi-device batch execution |
| **Database** | DuckDB 0.8 | Lightweight capability library |
| **Templates** | Jinja2 3.1 | HTML report generation |
| **Package Manager** | uv | Fast dependency management |

### Key Features

✅ **Small Core, Large Ecosystem** - Small core extended via Markdown  
✅ **Claude Code Compatible** - `.olav/` structure aligns with `.claude/`  
✅ **Multi-Vendor Support** - Cisco/Huawei/Arista/Juniper, etc.  
✅ **Intelligent Routing** - LLM automatically selects appropriate skills  
✅ **Production Ready** - Complete error handling, type hints, validation  
✅ **Easy to Extend** - Add new features by adding Markdown files  

---

## File Structure

```
OLAV/
├── .olav/                     # OLAV configuration and knowledge base
│   ├── OLAV.md               # Core system prompt
│   ├── skills/               # Core skills (Markdown)
│   │   ├── device-inspection.md      # L1-L4 inspection
│   │   ├── quick-query.md            # Fast queries
│   │   ├── deep-analysis.md          # Complex diagnostics
│   │   └── config-backup.md          # Configuration backup
│   ├── knowledge/            # Knowledge base
│   │   ├── aliases.md        # Device alias mapping
│   │   └── topology.md       # Network topology
│   ├── config/nornir/        # Nornir inventory config
│   ├── data/
│   │   └── configs/          # Backup storage directory
│   ├── reports/              # Generated HTML reports
│   └── capabilities.db       # DuckDB command library
│
├── src/olav/                 # Main source code
│   ├── agent.py             # DeepAgents agent creation
│   ├── main.py              # CLI entry point
│   ├── core/                # Core modules
│   └── tools/               # LangChain tools
│
├── i18n/                     # Internationalization
│   └── zh.md                # Chinese guide
│
├── tests/                    # Test suite
├── pyproject.toml           # Project configuration (uv)
└── README.md                # This file
```

---

## Quick Reference

### Common Commands

```bash
# 🚀 Start Interactive CLI
uv run python -m olav.main

# 📋 In CLI - View Available Devices
/devices
/devices [group]

# 📚 In CLI - Show Available Skills
/skills
/skills [skill_name]

# 🔍 In CLI - Quick Inspection
/inspect [layer|scope]

# 📁 In CLI - List Backups
/backups

# 📜 In CLI - Show Command History
/history

# 🧹 In CLI - Clear Memory
/clear

# ❓ In CLI - Help
/help

# 🚪 In CLI - Exit
/quit
```

---

## Support

### Troubleshooting

1. **Devices not found**: Check `.olav/config/nornir/hosts.yaml` and verify credentials in `.env`
2. **Commands timing out**: Increase SSH timeout in Nornir config
3. **Backup files not saving**: Verify `.olav/data/configs/` directory exists and is writable

### Common Issues

**Q: How do I add a new device?**
A: Edit `.olav/config/nornir/hosts.yaml` and add the device entry with group and role information.

**Q: Can I backup specific configuration sections?**
A: Use natural language in the skill: "Backup interface configs from core devices" - the skill will determine the best approach.

**Q: How are backups organized?**
A: All backups go to `.olav/data/configs/` with format `[device]-[config-type]-[timestamp].txt`

**Q: How do I migrate to Claude Code?**
A: Run `python scripts/migrate_olav_to_agent.py --platform claude` - it's automated and creates backups automatically!

**Q: What if migration fails?**
A: Use `--dry-run` first to preview, or restore from `.backup_*` directory if needed. See [AGENT_MIGRATION_GUIDE.md](AGENT_MIGRATION_GUIDE.md).

---

## Quick Reference - All Commands

### Migration & Setup
```bash
# Migrate to Claude Code
python scripts/migrate_olav_to_agent.py --platform claude

# Preview migration first (recommended)
python scripts/migrate_olav_to_agent.py --platform claude --dry-run

# Migrate to all platforms
python scripts/migrate_olav_to_agent.py --platform all

# Verify migration results
python scripts/verify_claude_compatibility.py .
pytest tests/ -v
```

### Knowledge Management
```bash
# Search knowledge base (hybrid: full-text + semantic)
python .olav/commands/search-knowledge.py "BGP configuration" --type hybrid

# Reload/update knowledge base
python .olav/commands/reload-knowledge.py --incremental

# Sync knowledge database
python .olav/commands/sync-knowledge.py --cleanup

# Get detailed report
python .olav/commands/reload-knowledge.py --incremental --report
```

### Testing
```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/unit/test_skill_loader.py -v

# Run with coverage report
pytest tests/ --cov=src/olav --cov-report=html

# Run only unit tests (fast)
pytest tests/unit/ -v
```

### Development Tools
```bash
# Code formatting (Ruff)
uv run ruff format .

# Code linting and fixing
uv run ruff check . --fix

# Type checking (Pyright)
uv run pyright

# Pre-commit check
uv run pre-commit run --all-files

# Verify entire project
python scripts/verify_migration_complete.py .
```

---

## New Features Checklist (v0.8.1)

- ✅ One-command migration to Claude Code: `python scripts/migrate_olav_to_agent.py --platform claude`
- ✅ Automatic backup before migration
- ✅ Dry-run mode for safe testing: `--dry-run`
- ✅ Support for multiple platforms: Claude, Cursor, others
- ✅ Knowledge base search with hybrid FTS + vector search
- ✅ Knowledge reload/sync utilities
- ✅ 80+ test cases covering all functionality
- ✅ Automated compatibility verification
- ✅ Comprehensive documentation (Chinese + English)
- ✅ Migration reports in JSON format

---

## License

MIT License - See LICENSE file for details

---

**OLAV v0.8** - *Build Network Intelligence with AI*  
**Last Updated**: 2026-01-09 | **Maintained by**: GitHub Copilot + Claude Haiku 4.5

---

## 中文快速指南 (Chinese Quick Guide)

### Claude Code 集成

OLAV 现已完全支持 **Claude Code**、**Cursor IDE** 等 Agent 平台！快速迁移命令：

```bash
# 1️⃣ 测试迁移（不修改文件）
python scripts/migrate_olav_to_agent.py --platform claude --dry-run

# 2️⃣ 执行迁移（自动备份）
python scripts/migrate_olav_to_agent.py --platform claude

# 3️⃣ 验证迁移结果
python scripts/verify_claude_compatibility.py .
pytest tests/ -v
```

### 主要特性

✨ **一键迁移脚本** - 自动转换为 Claude Code/Cursor 格式  
✨ **知识库搜索** - 混合搜索（全文 FTS + 向量语义）  
✨ **自动备份系统** - 迁移前自动备份原始文件  
✨ **兼容性验证** - 自动检查 Claude Code 格式兼容性  
✨ **完整测试套件** - 80+ 个测试用例确保质量  

### 新增工具

| 工具 | 功能 | 命令 |
|------|------|------|
| migrate_olav_to_agent.py | 一键迁移 | `python scripts/migrate_olav_to_agent.py --platform claude` |
| search-knowledge | 知识库搜索 | `python .olav/commands/search-knowledge.py "查询"` |
| reload-knowledge | 知识库更新 | `python .olav/commands/reload-knowledge.py --incremental` |
| sync-knowledge | 知识库同步 | `python .olav/commands/sync-knowledge.py --cleanup` |

### 详细中文文档

- [AGENT_MIGRATION_GUIDE.md](AGENT_MIGRATION_GUIDE.md) - 完整的迁移操作指南
- [CLAUDE_CODE_QUICK_START.md](CLAUDE_CODE_QUICK_START.md) - Claude Code 用户快速入门

---
