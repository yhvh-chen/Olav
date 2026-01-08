# 🤖 OLAV - Enterprise Network Operations AI Assistant

**Version**: 0.8.0  
**Status**: ✅ Phase 1-5 Production Ready  
**Architecture**: DeepAgents Native + Three-Layer Knowledge Architecture (Skills/Knowledge/Tools)  
**Platform**: Compatible with Claude Code, supports Windows/Mac/Linux  

**[中文指南](i18n/zh.md)** | **English Guide**

---

## 📋 Table of Contents

- [Quick Start](#quick-start)
- [Features](#features)
- [Development Phases](#development-phases)
- [Installation](#installation)
- [Usage Examples](#usage-examples)
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

### 2️⃣ Run Your First Command

```bash
# Query device status
uv run python -m olav.main "Check R1 interface status"

# Perform comprehensive inspection
uv run python -m olav.main "Inspect all lab devices"

# Search capability library
uv run python -m olav.main "How to check BGP neighbors?"
```

### 3️⃣ Use with Claude Code

```
1. Navigate to the project directory
2. Open in Claude Code
3. View available skills: `/skills/device-inspection`
4. Send command: "Inspect all lab devices with full L1-L4 health check"
```

---

## Features

### 🎯 Three Core Capabilities

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
"Show interface status on S1"
"Get BGP neighbors from R2"
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

---

## Development Phases

OLAV is developed in 5 progressive phases, each phase is fully production-ready:

### Phase 1: MVP (Core Framework) ✅
- **DeepAgents Agent** foundation
- **Skill routing system**
- **Basic command execution** (Nornir)
- **Knowledge base** (aliases/topology)
- **Status**: ✅ Production Ready

### Phase 2: Skill System ✅
- **Skill-based routing** - LLM intelligent routing
- **Bilingual support** - English/Chinese recognition
- **Three-layer knowledge architecture** - Skills/Knowledge/Tools
- **Multi-device support** - Automatic batch processing
- **Status**: ✅ Production Ready

### Phase 3: SubAgent Framework ✅
- **Macro analysis** - Topology-level path analysis
- **Micro diagnostics** - Device-level layered diagnostics
- **Backward compatibility** - Preserved original skills
- **Automatic fallback** - Graceful degradation
- **Status**: ✅ Production Ready

### Phase 4: Inspection Automation ✅
- **Comprehensive Inspection** - L1-L4 full coverage
- **Multi-device Reports** - Unified multi-device reports
- **Anomaly Detection** - Automatic anomaly flagging
- **HTML Report Generation** - Professional visualization
- **Status**: ✅ Production Ready

### Phase 5: Real Device Testing ✅
- **Real Nornir Integration** - Actual device connections
- **Real LLM API** - Genuine LLM calls
- **Complete E2E Testing** - 16+ real scenarios
- **DuckDB Capability Library** - CLI/API/NETCONF command library
- **Status**: ✅ Production Ready

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

# 5. Verify installation
uv run python -m olav.main "Check device connectivity"
```

---

## Usage Examples

### Example 1: Basic Device Query

```bash
# CLI mode
$ uv run python -m olav.main "R1 interface status"

# Expected output:
# R1 Gi0/1: UP, 1000Mbps
# R1 Gi0/2: UP, 1000Mbps
# R1 Gi0/3: DOWN
```

### Example 2: Comprehensive Device Inspection

```bash
# Perform L1-L4 comprehensive inspection on all lab devices
$ uv run python -m olav.main "Inspect all lab devices with comprehensive L1-L4 check"

# Generated reports:
# .olav/reports/lab-comprehensive-l1l4-20260108-143000.html
#   ├─ Executive Summary (overall status of all 8 devices)
#   ├─ L1-L4 layered data
#   ├─ Anomaly detection and flagging
#   └─ Remediation suggestions
```

### Example 3: Deep Analysis Workflow

```bash
# Complex multi-step diagnostics
$ uv run python -m olav.main "Diagnose why BGP is flapping on R1 and provide remediation steps"

# Expected workflow:
# 1. Check BGP peer status
# 2. Analyze interface stability
# 3. Review routing table
# 4. Check CPU/memory on router
# 5. Provide recommendations
```

### Example 4: Using with Claude Code

```
Claude Code prompt:

"Use OLAV skills to:
1. Inspect all lab devices
2. Generate comprehensive health report
3. Flag any anomalies
4. Provide remediation suggestions"

Expected result:
✅ Agent automatically matches device-inspection skill
✅ Lists all lab group devices
✅ Executes L1-L4 inspection
✅ Generates HTML report to .olav/reports/
✅ Extracts anomalies and suggests remediation
```

---

## 架构设计

### 三层知识架构
Architecture

### Three-Layer Knowledge Architecture

```
┌────────────────────────────────────────────────────────┐
│          OLAV Three-Layer Knowledge Architecture        │
├────────────────────────────────────────────────────────┤
│                                                        │
│  Layer 1: SKILLS (.olav/skills/*.md)                  │
│  ├─ device-inspection    → Comprehensive L1-L4 check  │
│  ├─ quick-query          → Fast 1-2 command queries   │
│  └─ deep-analysis        → Multi-step diagnostics     │
│     [Strategy Layer - HOW: How to execute tasks]       │
│                                                        │
│  Layer 2: KNOWLEDGE (.olav/knowledge/*.md)            │
│  ├─ aliases.md           → Device alias mapping       │
│  ├─ topology.md          → Network topology           │
│  └─ platform-commands.md → Multi-vendor command lib   │
│     [Knowledge Layer - WHAT: What are facts]          │
│                                                        │
│  Layer 3: TOOLS/CAPABILITIES                          │
│  ├─ Nornir               → SSH batch execution        │
│  ├─ DuckDB              → CLI/API/NETCONF library     │
│  ├─ Jinja2              → Report template generation  │
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
   Technology Stack

### Core Technologies

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Framework** | DeepAgents | Agent orchestration and HITL |
| **LLM** | OpenAI/Claude | Intent recognition and routing |
| **Network** | Nornir 3.3 | Multi-device batch execution |
| **Database** | DuckDB 0.8 | Lightweight capability library |
| **Templates** | Jinja2 3.1 | HTML report generation |
| **Testing** | Pytest 9.0 | Complete E2E testing |
| **Package Manager** | uv | Fast dependency management |
| **Code Quality** | Ruff | Linting + formatting |

### Key Features

✅ **Small Core, Large Ecosystem** - Small core extended via Markdown  
✅ **Claude Code Compatible** - `.olav/` structure aligns with `.claude/`  
✅ **Multi-Vendor Support** - Cisco/Huawei/Arista/Juniper, etc.  
✅ **Intelligent Routing** - LLM automatically selects appropriate skills  
✅ **Production Ready** - Complete testing, type checking, error handling  
✅ **Easy to Extend** - Add new features by adding Markdown files  

---

## File Structure

```
OLAV/
├── .olav/                     # OLAV configuration and knowledge base
│   ├── OLAV.md               # Core system prompt
│   ├── skills/               # 3 core skills (Markdown)
│   │   ├── device-inspection.md
│   │   ├── quick-query.md
│   │   └── deep-analysis.md
│   ├── knowledge/            # Knowledge base
│   │   ├── aliases.md        # Device aliases
│   │   └── topology.md       # Network topology
│   ├── config/nornir/        # Nornir inventory config
│   ├── reports/              # Generated HTML reports
│   └── capabilities.db       # DuckDB command library
│
├── src/olav/                 # Main source code
│   ├── agent.py             # DeepAgents creation
│   ├── core/                # Core modules
│   ├── tools/               # LangChain tools
│   └── main.py              # CLI entry point
│
├── i18n/                     # Internationalization
│   └── zh.md                # Chinese guide
│
├── pyproject.toml           # Project configuration (uv)
└── README.md                # This file
```

---

## Quick Reference

### Common Commands

```bash
# Start OLAV CLI
uv run python -m olav.main

# Perform device inspection
uv run python -m olav.main "Inspect all lab devices"

# Query single device
uv run python -m olav.main "Check R1 status"

# Code quality checks
uv run ruff check src/ --fix

# Type checking
uv run mypy src/ --strict
```

---

## Support

### Troubleshooting

1. **Check logs**: `tail -f nornir.log`
2. **Verify configuration**: `.env` and `.olav/config/nornir/`
3. **Run diagnostics**: `uv run python -m olav.main "Test connectivity"`

### Feedback

- **Report Issues**: Describe the problem and reproduction steps
- **Contribute**: Ensure code quality and tests pass
- **Discuss Features**: Share your ideas

---

## License

MIT License - See LICENSE file for details

---

## Acknowledgments

- **DeepAgents Framework**: Powerful agent orchestration capabilities
- **Claude Code**: Inspired the three-layer knowledge architecture design
- **Nornir**: Excellent network automation framework
- **LangChain**: Flexible LLM integration

---

**OLAV v0.8** - *Build Network Intelligence with AI*

**Last Updated**: 2026-01-08 | **Maintained by
**OLAV v0.8** - *Build Network Intelligence with AI*

**最后更新**: 2026-01-08 | **维护者**: GitHub Copilot + Claude Haiku 4.5
