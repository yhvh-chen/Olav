# Changelog

All notable changes to OLAV (NetAIChatOps) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.0-beta] - 2025-12-08

### Added

- **New Branding**: Renamed from "Omni-Layer Autonomous Verifier" to "NetAIChatOps"
- **Role-Based Access Control**: Three user roles (admin, operator, viewer) with permission matrix
  - Admin: Full access, can skip HITL approval
  - Operator: Read-write with HITL confirmation
  - Viewer: Read-only, cannot trigger write workflows
- **Admin CLI Tool** (`olav-admin`): Server-side administration commands
  - `olav-admin token create/list/revoke` - Session token management
  - `olav-admin master-token` - Master token management
  - `olav-admin init` - Database/index initialization
- **Unified Doctor Command** (`olav doctor`): System health check (merged `status` + `doctor`)
  - Checks Server connectivity and authentication status
  - Checks PostgreSQL, OpenSearch, Redis (optional), NetBox, LLM provider
  - Supports `--json` output for scripting
  - Colored status output with Rich tables
- **REPL Mode** (`olav repl`): Lightweight interactive mode without full dashboard
- **Unified Configuration** (`config/settings.py`): Single entry point for all settings
  - All configuration via `.env` environment variables
  - Typed configuration with Pydantic EnvSettings
- **CLI Entry Point** (`cli.py`): Simple entry point for CLI commands
  - Usage: `uv run cli.py` or `python cli.py`
- **Quick Start Commands**: `make quickstart`, `make deploy`, `make doctor`
- **OpenSearch Basic Auth**: Support for `OPENSEARCH_USERNAME/PASSWORD` and `OPENSEARCH_VERIFY_CERTS`
- **OpenSearch Client Factory** (`create_opensearch_client`): Shared factory function in `olav.core.memory`
  - All ETL scripts now use unified client creation with auth support
  - Eliminates duplicate OpenSearch client initialization code
- **OpenSearch Security Enabled by Default**: Docker container now starts with authentication
  - Default credentials: `admin` / `OlavOS123!`
  - SSL/TLS disabled for development (use reverse proxy for production)

### Changed

- Version bumped to 0.5.0-beta
- Updated all branding references across codebase (8+ files)
- CLI entry points reorganized:
  - `olav` - Main CLI with dashboard
  - `olav-admin` - Server administration
  - `olav-server` - API server (FastAPI)
- **CLI Command Consolidation**:
  - `status` merged into `doctor` (use `olav doctor` for all health checks)
  - `banner` merged into `version` (use `olav version --banner` for ASCII art)
- **Redis now optional**: Use `docker-compose --profile cache up -d` to enable
  - Falls back to in-memory cache when Redis unavailable
  - Single-instance deployments can skip Redis entirely
- Permission checks added to SSE stream and invoke endpoints

### Fixed

- Windows async compatibility with `WindowsSelectorEventLoopPolicy`
- Test evaluation assertions made conditional for mock environments
- OpenSearch connections now properly handle TLS verification

### Security

- Session tokens now include role field
- Viewer role blocked from expert mode and write workflows
- Permission validation at API endpoint level

## [0.4.0] - 2025-11-XX

### Added

- LangGraph-based workflow orchestration
- Dynamic intent routing with semantic similarity
- SuzieQ integration for network state analysis
- NETCONF/CLI execution with HITL approval

### Changed

- Migrated from legacy agent architecture to LangGraph workflows
- Unified all CLI commands under Typer framework

## [0.3.0] - 2025-10-XX

### Added

- Initial ChatOps implementation
- Basic CLI interface
- OpenSearch integration for vector search

---

## Migration Guide

### From 0.4.x to 0.5.0

1. **Update Configuration**:
   - All configuration now in `config/settings.py` with EnvSettings
   - Sensitive data remains in `.env`
   - Use `from config.settings import settings` for unified access

2. **Token Management**:
   - Use `olav-admin token create` to create session tokens
   - Session tokens now include role (admin/operator/viewer)
   - Register endpoint updated to accept role parameter

3. **CLI Changes**:
   - New `olav repl` command for lightweight REPL mode
   - `olav doctor` for system health check
   - Dashboard mode remains default for `olav` command

4. **Permissions**:
   - Viewer role users cannot access expert mode
   - Write workflows require operator or admin role
