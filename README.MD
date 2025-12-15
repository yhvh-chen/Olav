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

OLAV is an intelligent network operations assistant that orchestrates complex workflows using **LangGraph**, **SuzieQ** for observability, and **NetBox** as the Single Source of Truth. It implements a "Safety First" philosophy with Human-in-the-Loop (HITL) controls for all configuration changes.

## 🌟 Key Features

- **Workflow Orchestration**: Powered by LangGraph to handle complex, multi-step network investigations.
- **Schema-Aware Tools**: Uses universal tools to query SuzieQ and OpenConfig schemas dynamically, avoiding tool proliferation.
- **Safety First**: All write operations (NETCONF/CLI) require explicit HITL approval.
- **Funnel Debugging**: Macro analysis (SuzieQ) → Micro diagnostics (NETCONF).
- **Single Source of Truth**: Deep integration with NetBox for inventory and credentials.

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
   cp .env.example .env
   
   # Install dependencies
   uv sync --dev
   ```

2. **Start Infrastructure**
   ```bash
   docker-compose up -d
   ```

3. **Initialize & Run**
   ```bash
   # Windows
   .\setup.ps1
   
   # Linux/Mac
   ./setup.sh
   
   # Start CLI
   uv run olav
   ```

## 📚 Documentation

For detailed installation instructions, production deployment, and advanced usage, please refer to the **[User Guide](USER_GUIDE.md)**.

## 🏗 Architecture

OLAV uses a modular architecture:
- **Orchestrator**: Routes user intents to specialized workflows.
- **Agents**: Specialized agents for Querying, Device Execution, and NetBox management.
- **Memory**: PostgreSQL-based checkpointer for state persistence.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
