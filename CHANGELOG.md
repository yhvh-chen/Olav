# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.8.0] - 2026-01-11

### Added
- **DeepAgents Integration**: Full integration with DeepAgents framework for subagent orchestration
- **Three-Layer Knowledge Architecture**:
  - Skills (`.olav/skills/*.md`): Strategies & SOPs
  - Knowledge (`.olav/knowledge/*.md`): Facts & Context
  - Capabilities (Python/DB): Execution & Tools
- **Interactive CLI**: Enhanced command-line interface with Rich formatting
  - `/analyze`: Deep diagnosis with MicroAnalyzer sub-agent
  - `/inspect`: Quick L1-L4 health checks
  - `/backup`: Configuration backup workflow
  - `/search`: Knowledge base and web search
  - `/devices`: Device inventory management
  - `/skills`: View loaded AI capabilities
- **Multi-Vendor Network Support**: Cisco, Huawei, Juniper, Arista via Nornir/Netmiko
- **Knowledge Base Integration**: DuckDB-powered vector search with embedding support
- **Inspection Skills**: Markdown-defined health check procedures
- **Report Formatter**: Multi-format output (Markdown, JSON, Table)
- **Human-in-the-Loop (HITL)**: Approval workflow for write operations
- **Docker & Kubernetes Deployment**: Production-ready container configurations

### Changed
- Migrated from legacy architecture to DeepAgents Native Architecture
- Unified CLI entry point via `uv run olav.py`
- Improved test coverage to 80%+
- Updated Ruff configuration to use new lint section format

### Fixed
- Closure variable binding in smart_query.py
- Type annotations for public functions
- Code style issues (trailing whitespace, blank lines)

### Security
- Shell command execution is intentional for CLI tool functionality
- Sensitive configuration managed via `.env` files
- K8s Secrets for production credential management

### Documentation
- Comprehensive README with quick start guide
- Detailed architecture documentation (DESIGN_V0.8.md)
- CLI user guide and command reference
- Chinese language support (i18n/zh.md)

## [0.7.0] - 2025-12-01

### Added
- Initial Nornir integration for network automation
- Basic CLI interface
- LLM provider abstraction (OpenAI, Ollama)

### Changed
- Refactored project structure for modularity

## [0.6.0] - 2025-10-15

### Added
- Prototype network diagnostic capabilities
- Basic skill loading system

---

For more details, see the [full documentation](docs/README.md).
