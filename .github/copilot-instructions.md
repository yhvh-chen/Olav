# OLAV AI Coding Agent Instructions

## Project Overview

OLAV (Omni-Layer Autonomous Verifier) is an enterprise network operations ChatOps platform using **LangGraph Workflows** for orchestration. It follows a **Schema-Aware** architecture to avoid tool proliferation and implements **漏斗式排错** (Funnel Debugging): macro analysis (SuzieQ) → micro diagnostics (NETCONF).

**Core Philosophy**: Safety First - all write operations require **HITL (Human-in-the-Loop)** approval via LangGraph interrupts.

## Architecture Essentials

### Workflow Orchestration Pattern

Use `WorkflowOrchestrator` from `root_agent_orchestrator.py` - orchestrates multiple specialized workflows:

```python
from olav.agents.root_agent_orchestrator import create_workflow_orchestrator
from langgraph.checkpoint.postgres import PostgresSaver

# All workflows share PostgreSQL Checkpointer for state persistence
checkpointer = PostgresSaver.from_conn_string(os.getenv("POSTGRES_URI"))

orchestrator = create_workflow_orchestrator(checkpointer=checkpointer)

# Available workflows:
# - QueryDiagnosticWorkflow: SuzieQ-based network diagnostics (read-only)
# - DeviceExecutionWorkflow: NETCONF/CLI execution with HITL
# - NetBoxManagementWorkflow: NetBox SSOT operations with HITL
# - DeepDiveWorkflow: Complex multi-step investigations with recursion

result = await orchestrator.run(user_query="查询 R1 BGP 状态")
```

**Workflow Selection**: Intent classifier (LLM-based) routes queries to appropriate workflow based on user intent.

### Schema-Aware Tool Design

**CRITICAL**: Use 2 universal tools instead of 120+ resource-specific tools:

```python
# ❌ WRONG: Creating individual tools for each resource
def query_interfaces(...): ...
def query_bgp(...): ...
def query_routes(...): ...  # 120+ tools = maintenance nightmare

# ✅ CORRECT: Schema-Aware pattern (see src/olav/tools/suzieq_tool.py)
@tool
def suzieq_query(table: str, method: Literal['get', 'summarize', 'unique', 'aver'], **filters):
    """Universal query tool - LLM discovers tables via suzieq_schema_search first"""
    sq_obj = get_sqobject(table)(context=self.ctxt)
    return sq_obj.get(**filters) if method == 'get' else sq_obj.summarize(**filters)

@tool
def suzieq_schema_search(query: str) -> Dict:
    """Returns available tables/fields from suzieq.shared.schema.Schema"""
    return {"tables": schema.tables(), "fields": schema.get_raw_schema(table), ...}
```

**Why**: SuzieQ has 30+ tables with 4 methods each = 120+ tools. Schema-Aware approach: LLM queries schema index → discovers fields → constructs query dynamically. Same pattern applies to OpenConfig YANG schemas.

### Prompt Management System

**ALL prompts go in `config/prompts/`** - zero hardcoded prompts in Python:

```python
# src/olav/core/prompt_manager.py (LangChain PromptTemplate)
from olav.core.prompt_manager import prompt_manager

# Agent prompts
system_prompt = prompt_manager.load_agent_prompt(
    "root_agent",  # Loads config/prompts/agents/root_agent.yaml
    user_name=current_user,
    network_context=get_network_context()
)

# Tool descriptions
tool_desc = prompt_manager.load_tool_description(
    "suzieq_query",  # Loads config/prompts/tools/suzieq_query.yaml
    available_tables=", ".join(schema.tables()),
    example_usage="suzieq_query(table='bgp', method='summarize')"
)
```

**Prompt Template Format** (YAML):
```yaml
_type: prompt
input_variables:
  - user_name
  - network_context
template: |
  你是企业网络运维专家 OLAV...
  操作员: {user_name}
  上下文: {network_context}
```

### HITL Safety Pattern

**SuzieQ**: Read-only (Parquet queries) → **NO sandbox needed**
**Nornir**: Read-write (NETCONF) → **Requires NornirSandbox + HITL**

```python
# src/olav/execution/backends/nornir_sandbox.py
class NornirSandbox(SandboxBackendProtocol):
    async def execute(self, command: str, requires_approval: bool = True):
        is_write = self._is_write_operation(command)
        
        if is_write and requires_approval:
            # Trigger LangGraph interrupt
            approval = await self._request_approval(command)
            if approval.decision == "reject":
                return ExecutionResult(success=False, output="User rejected")
        
        # Log to OpenSearch audit index
        self._log_execution(command, is_write)
        return self.nr.run(task=netconf_task, payload=command)
```

**Workflow HITL Configuration**: Write operations in DeviceExecutionWorkflow and NetBoxManagementWorkflow automatically trigger HITL interrupts.

## Developer Workflows

### Package Management with uv

**CRITICAL**: This project uses `uv` (ultra-fast Python package manager), NOT pip/poetry/pipenv:

```bash
# Install uv (if not installed)
curl -LsSf https://astral.sh/uv/install.sh | sh  # Linux/Mac
# Or: pip install uv  # If you must use pip

# First-time setup
uv sync                    # Install all dependencies from pyproject.toml
uv sync --dev              # Include dev dependencies (pytest, ruff, etc.)

# Add new dependencies
uv add langchain           # Runtime dependency
uv add --dev pytest        # Dev dependency
uv add "openai>=1.0"       # With version constraint

# Update dependencies
uv lock                    # Update uv.lock
uv sync                    # Apply lock file changes

# Run commands in uv environment
uv run olav.py                         # Run CLI (normal mode)
uv run olav.py -e "complex query"      # Run CLI (expert mode with Deep Dive)
uv run pytest                          # Run tests
uv run ruff check src/                 # Lint code
```

**CLI Modes**:
- **Normal Mode** (default): 3 standard workflows (Query/Execution/NetBox)
- **Expert Mode** (`-e/--expert`): Enables DeepDiveWorkflow for complex tasks
  - Automatic task decomposition
  - Recursive diagnostics (max 3 levels)
  - Batch audits (30+ devices parallel)
  - Progress tracking with resume capability

**Why uv?**
- 10-100x faster than pip
- Built-in virtual environment management (no manual `venv` needed)
- Lockfile for reproducible builds (`uv.lock`)
- Compatible with `pyproject.toml` standards

### Docker Initialization

```bash
# 1. Start base services
docker-compose up -d opensearch postgres redis suzieq

# 2. Run init container (one-time setup)
docker-compose --profile init up olav-init
# This executes sequentially:
#   - init_postgres.py (Checkpointer tables)
#   - init_schema.py (OpenConfig YANG → openconfig-schema index)
#   - suzieq_schema_etl.py (Avro Schema → suzieq-schema index)

# 3. Verify initialization
docker-compose exec postgres psql -U olav -d olav -c "\dt"
# Should show: checkpoints, checkpoint_writes, checkpoint_migrations

curl http://localhost:9200/_cat/indices?v | grep schema
# Should show: openconfig-schema, suzieq-schema
```

### Local Development (Without Docker)

```bash
# 1. Setup environment
uv sync --dev

# 2. Start infrastructure (using Docker for services only)
docker-compose up -d opensearch postgres redis

# 3. Run init scripts locally
uv run python -m olav.etl.init_postgres
uv run python -m olav.etl.init_schema
uv run python -m olav.etl.suzieq_schema_etl

# 4. Run OLAV CLI
uv run olav.py                         # Normal mode (interactive)
uv run olav.py "查询 R1 接口状态"       # Normal mode (single query)
uv run olav.py -e "审计所有边界路由器"  # Expert mode (Deep Dive)

# 5. Run specific agent tests
uv run pytest tests/unit/test_agents.py -v

# 6. Code quality checks
uv run ruff check src/ --fix    # Auto-fix issues
uv run ruff format src/          # Format code
uv run mypy src/                 # Type checking
```

### NetBox as Single Source of Truth

**Both Nornir and SuzieQ read from NetBox** - no dual inventory management:

```yaml
# config/nornir_config.yml
plugin: NBInventory
nb_url: ${NETBOX_URL}
nb_token: ${NETBOX_TOKEN}
filter_parameters:
  tag: ["olav-managed"]

# config/suzieq_config.yml
sources:
  - name: production-netbox
    type: netbox
    url: ${NETBOX_URL}
    token: ${NETBOX_TOKEN}
    tag: ["suzieq-monitor"]
```

### ETL Scripts Location

All ETL scripts in `src/olav/etl/`:
- `init_postgres.py`: PostgresSaver.setup() for Checkpointer tables
- `init_schema.py`: Clone OpenConfig repos → parse YANG → index XPaths
- `suzieq_schema_etl.py`: Parse `suzieq/config/schema/*.avsc` → index to OpenSearch

### Knowledge Base Architecture

Three-tier RAG (priority order):
1. **Memory Index** (`olav-episodic-memory`): Historical success paths (User Intent → XPath)
2. **Schema Index** (`openconfig-schema`, `suzieq-schema`): Ground truth from YANG/Avro
3. **Docs Index** (`olav-docs`): Vendor manuals, RFCs (from `data/documents/`)

## Critical Patterns

### Backend Protocol Stack

Protocol-based dependency injection pattern:

```python
# src/olav/execution/backends/protocol.py
class BackendProtocol(Protocol):
    async def read(self, path: str) -> str: ...
    async def write(self, path: str, content: str) -> None: ...

class SandboxBackendProtocol(BackendProtocol, Protocol):
    async def execute(self, command: str, background: bool = False) -> ExecutionResult: ...

class StoreBackendProtocol(BackendProtocol, Protocol):
    async def put(self, namespace: str, key: str, value: dict) -> None: ...
```

Implementations:
- `StateBackend`: LangGraph State (dev)
- `RedisBackend`: Redis + OpenSearch (prod)
- `NornirSandbox`: NETCONF execution with HITL

### Workflow-Specific Middleware

Workflows can include custom middleware for context enrichment:

```python
# Example: Network context middleware for device operations
class NetworkContextMiddleware:
    async def enrich_context(self, state: dict) -> dict:
        device = state.get('device')
        if device:
            topology = await self.get_topology_context(device)
            state['network_context'] = topology
        return state
```

### LLM Factory Pattern

Support OpenAI/Ollama/Azure via single factory (`src/olav/core/llm.py`):

```python
class LLMFactory:
    @staticmethod
    def get_chat_model(json_mode: bool = False):
        if settings.LLM_PROVIDER == "openai":
            return ChatOpenAI(model=settings.LLM_MODEL_NAME, ...)
        elif settings.LLM_PROVIDER == "ollama":
            return ChatOllama(model=settings.LLM_MODEL_NAME, format="json" if json_mode else None)
    
    @staticmethod
    def get_embedding_model():
        return OpenAIEmbeddings() if settings.LLM_PROVIDER == "openai" else ...
```

## Testing Conventions

**Test Structure**: `tests/unit/` for unit tests, `tests/e2e/` for integration tests

```bash
# Run all tests
uv run pytest

# Run with verbose output
uv run pytest -v

# Test specific module
uv run pytest tests/unit/test_agents.py

# Test specific function
uv run pytest tests/unit/test_agents.py::test_suzieq_agent -v

# Test with coverage report
uv run pytest --cov=src/olav --cov-report=html --cov-report=term

# Run only failed tests from last run
uv run pytest --lf

# Run tests matching pattern
uv run pytest -k "suzieq or schema"

# Watch mode (requires pytest-watch)
uv run ptw -- --testmon
```

**Test Fixtures**: Use `conftest.py` for shared fixtures:

```python
# tests/conftest.py
import pytest
from langgraph.checkpoint.postgres import PostgresSaver

@pytest.fixture
def checkpointer():
    """Shared PostgreSQL checkpointer for tests"""
    with PostgresSaver.from_conn_string("postgresql://test:test@localhost:5432/test") as saver:
        saver.setup()
        yield saver

@pytest.fixture
def mock_suzieq_context():
    """Mock SuzieQ context for testing"""
    # Mock implementation
    pass
```

**Async Testing**: Use `pytest-asyncio` for async agent tests:

```python
import pytest

@pytest.mark.asyncio
async def test_workflow_execution(checkpointer):
    orchestrator = create_workflow_orchestrator(checkpointer=checkpointer)
    result = await orchestrator.run(user_query="查询 R1 BGP 状态")
    assert result["messages"][-1].content
```

## Python Best Practices

### Code Quality Standards

```bash
# Format code (Black-compatible)
uv run ruff format src/ tests/

# Lint and auto-fix
uv run ruff check src/ tests/ --fix

# Type checking
uv run mypy src/ --strict

# All-in-one quality check
uv run ruff check src/ && uv run ruff format src/ --check && uv run mypy src/
```

**Ruff Configuration** (pyproject.toml):
```toml
[tool.ruff]
line-length = 100
target-version = "py311"
select = ["E", "F", "I", "N", "W", "UP", "ANN", "ASYNC", "S", "B"]
ignore = ["ANN101", "ANN102"]  # Self/cls annotations

[tool.ruff.per-file-ignores]
"tests/**/*.py" = ["S101"]  # Allow assert in tests
```

### Type Hints

**ALWAYS use type hints** - this is a strictly typed codebase:

```python
from typing import Dict, List, Literal, Protocol
from langchain_core.messages import BaseMessage

# ✅ CORRECT
async def execute(
    self,
    command: str,
    background: bool = False,
    requires_approval: bool = True
) -> ExecutionResult:
    ...

# ❌ WRONG - missing type hints
async def execute(self, command, background=False):
    ...
```

### Async/Await Patterns

Use `async/await` for all I/O operations:

```python
# ✅ CORRECT - async for external calls
async def query_opensearch(self, index: str, query: Dict) -> List[Dict]:
    async with self.client.search(index=index, body=query) as response:
        return response["hits"]["hits"]

# ❌ WRONG - blocking I/O in async context
def query_opensearch(self, index: str, query: Dict):
    return requests.post(f"{self.url}/{index}/_search", json=query)
```

### Dependency Injection

Use Protocol types for dependency injection (not concrete classes):

```python
from typing import Protocol

# Define protocol
class BackendProtocol(Protocol):
    async def read(self, path: str) -> str: ...
    async def write(self, path: str, content: str) -> None: ...

# Accept protocol, not concrete class
class Agent:
    def __init__(self, backend: BackendProtocol):
        self.backend = backend
```

## Common Pitfalls

1. **Don't create individual tools for each network resource** - use Schema-Aware pattern
2. **Don't hardcode prompts in Python** - use `config/prompts/` + PromptManager
3. **Don't write custom LangGraph state machines** - use workflow orchestrator pattern
4. **Don't use MemorySaver** - dev/prod both use PostgreSQL Checkpointer for consistency
5. **Don't skip HITL for write operations** - workflows automatically trigger HITL for write ops
6. **Don't duplicate NetBox inventory** - both Nornir and SuzieQ read from same NetBox
7. **Don't use pip/poetry** - this project uses `uv` exclusively
8. **Don't skip type hints** - all functions must have full type annotations
9. **Don't use blocking I/O** - use `async/await` for external calls (OpenSearch, PostgreSQL, LLM)
10. **Don't import from `archive/`** - these are reference implementations only

## Key Files Reference

- **Workflow orchestration**: `src/olav/agents/root_agent_orchestrator.py`
- **Schema-Aware tools**: `src/olav/tools/suzieq_tool.py` (2 universal tools)
- **Prompt management**: `src/olav/core/prompt_manager.py` + `config/prompts/`
- **HITL sandbox**: `src/olav/execution/backends/nornir_sandbox.py`
- **ETL pipeline**: `src/olav/etl/init_postgres.py`, `init_schema.py`, `suzieq_schema_etl.py`
- **Backend protocols**: `src/olav/execution/backends/protocol.py`

## Project Structure Best Practices

### Module Organization

```
src/olav/
├── __init__.py              # Package exports
├── main.py                  # CLI entry point (Typer)
├── core/                    # Core abstractions (no business logic)
│   ├── llm.py              # LLM factory pattern
│   ├── prompt_manager.py   # Prompt template loader
│   └── settings.py         # Pydantic settings
├── agents/                  # Agent implementations
│   ├── root_agent.py       # Main orchestrator
│   └── middleware/         # Custom middleware
├── tools/                   # LangChain tools
│   ├── suzieq_tool.py      # Schema-aware SuzieQ tools
│   └── nornir_tool.py      # NETCONF/gNMI tools
├── execution/              # Backend layer
│   └── backends/
│       ├── protocol.py     # Protocol definitions
│       └── nornir_sandbox.py
└── etl/                    # Data pipelines
    ├── init_postgres.py
    └── init_schema.py
```

### Import Conventions

```python
# ✅ CORRECT - absolute imports from src root
from olav.core.llm import LLMFactory
from olav.tools.suzieq_tool import SuzieQSchemaAwareTool
from olav.execution.backends.protocol import BackendProtocol

# ❌ WRONG - relative imports across packages
from ..core.llm import LLMFactory
from ...tools import suzieq_tool
```

### Configuration Management

**Use Pydantic Settings** - never hardcode configuration:

```python
# config/settings.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )
    
    # LLM Configuration
    llm_provider: Literal["openai", "ollama", "azure"]
    llm_api_key: str
    llm_model_name: str = "gpt-4-turbo"
    
    # Infrastructure
    postgres_uri: str
    opensearch_url: str
    netbox_url: str
    netbox_token: str

settings = Settings()  # Auto-loads from .env
```

## Environment Setup

```bash
# 1. Clone and setup
git clone <repo>
cd Olav
uv sync --dev

# 2. Create .env from template
cp .env.example .env
# Edit .env with your credentials

# 3. Start infrastructure
docker-compose up -d opensearch postgres redis

# 4. Initialize databases
docker-compose --profile init up olav-init

# 5. Verify setup
uv run olav.py --version
```

**Required environment variables** (.env):
```bash
# LLM Configuration
LLM_PROVIDER=openai              # openai|ollama|azure
LLM_API_KEY=sk-...
LLM_MODEL_NAME=gpt-4-turbo

# Infrastructure
POSTGRES_URI=postgresql://olav:OlavPG123!@localhost:5432/olav
OPENSEARCH_URL=http://localhost:9200
REDIS_URL=redis://localhost:6379

# NetBox (Single Source of Truth)
NETBOX_URL=https://netbox.company.com
NETBOX_TOKEN=your_token_here

# Device Credentials
DEVICE_USERNAME=admin
DEVICE_PASSWORD=secure_password
```

## Quick Reference Commands

```bash
# Development
uv sync --dev                              # Install dependencies
uv run olav.py                             # Start CLI (normal mode)
uv run olav.py -e "complex task"           # Start CLI (expert mode)
uv run pytest -v                          # Run tests
uv run ruff check src/ --fix              # Lint and fix

# Docker Operations
docker-compose up -d                       # Start services
docker-compose --profile init up olav-init # Initialize
docker-compose logs -f olav-app            # View logs
docker-compose exec olav-app bash          # Shell into container

# Database Operations
docker-compose exec postgres psql -U olav -d olav -c "\dt"
curl http://localhost:9200/_cat/indices?v | grep schema

# Add Dependencies
uv add langchain-openai                    # Runtime dep
uv add --dev pytest-asyncio                # Dev dep
```

For detailed architecture, see comprehensive `README.MD` (2300+ lines with Chinese/English documentation).
