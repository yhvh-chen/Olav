"""Pytest configuration and shared fixtures.

Adds `src/` to `sys.path` so tests can import the project package
without requiring installation. This avoids `ModuleNotFoundError`
for `olav.*` modules when running tests directly from the repo.
"""

import os
import sys

import pytest
from langgraph.checkpoint.postgres import PostgresSaver

# Ensure both `src` and project root are on the import path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_PATH = os.path.join(PROJECT_ROOT, "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)
# Add project root for config.settings imports
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# If a top-level module file (olav.py) was imported before the package,
# remove it so the package directory `olav/` can be imported.
import importlib

if "olav" in sys.modules and not hasattr(sys.modules["olav"], "__path__"):
    del sys.modules["olav"]

# Safe/import-tolerant fallbacks to avoid hard failures in minimal test contexts
try:  # pragma: no cover - defensive import
    from olav.core.memory import OpenSearchMemory  # type: ignore
except Exception:  # pragma: no cover
    class OpenSearchMemory:  # type: ignore
        def __init__(self, url: str) -> None:  # minimal stub
            self.url = url

try:  # pragma: no cover - defensive import
    from config.settings import EnvSettings, settings  # type: ignore
except Exception:  # pragma: no cover
    class EnvSettings:  # type: ignore
        def __init__(self, **kwargs) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)
    settings = None  # Will use defaults


@pytest.fixture
def test_settings() -> EnvSettings:
    """Test settings loaded from environment (via config.settings).

    Uses the real EnvSettings which reads from .env file, ensuring
    tests use the same configuration as the running services.
    """
    if settings is not None:
        return settings
    # Fallback for minimal test contexts
    return EnvSettings(
        llm_provider="openai",
        llm_api_key="test-key",
        postgres_uri=os.getenv("POSTGRES_URI", "postgresql://olav:OlavPG123!@localhost:55432/olav"),
        opensearch_url=os.getenv("OPENSEARCH_URL", "http://localhost:19200"),
        redis_url=os.getenv("REDIS_URL", ""),
    )


@pytest.fixture
async def checkpointer():
    """Shared PostgreSQL checkpointer for tests.

    Uses postgres_uri from EnvSettings to ensure consistency with
    the running PostgreSQL container.
    """
    # Get connection string from settings or environment
    if settings is not None:
        conn_string = settings.postgres_uri
    else:
        conn_string = os.getenv("POSTGRES_URI", "postgresql://olav:OlavPG123!@localhost:55432/olav")

    try:
        async with PostgresSaver.from_conn_string(conn_string) as saver:
            await saver.setup()
            yield saver
    except Exception as e:
        pytest.skip(f"PostgreSQL not available: {e}")


@pytest.fixture
def opensearch_memory() -> OpenSearchMemory:
    """OpenSearch memory instance using settings from environment."""
    if settings is not None:
        url = settings.opensearch_url
    else:
        url = os.getenv("OPENSEARCH_URL", "http://localhost:19200")
    return OpenSearchMemory(url=url)


@pytest.fixture
def mock_suzieq_context():
    """Mock SuzieQ context for testing."""
    # TODO: Implement mock SuzieQ context


@pytest.fixture(autouse=True)
def reset_tool_registry():
    """Ensure ToolRegistry is populated before each test.

    Problem: Tools register themselves at module import time via:
        ToolRegistry.register(SuzieQTool())

    This causes state pollution when running full test suite because:
    1. Import order is non-deterministic
    2. Some tests may run before tool modules are imported
    3. Registration tests expect specific tools to be registered

    Solution: Import tool modules at test start (without reload) to ensure
    registration happens. Don't clear registry to avoid breaking isinstance checks.
    """
    # Import tool modules to trigger registration (if not already done)
    # importlib.import_module handles already-imported modules gracefully
    from olav.tools.base import ToolRegistry

    tool_modules = [
        "olav.tools.suzieq_tool",
        "olav.tools.netbox_tool",
        "olav.tools.nornir_tool",
        "olav.tools.opensearch_tool",
    ]

    for module_name in tool_modules:
        try:
            importlib.import_module(module_name)
        except Exception as e:
            # Log import errors for debugging
            print(f"Warning: Failed to import {module_name}: {e}")

    # Debug: Print registered tools
    registered_tools = [t.name for t in ToolRegistry.list_tools()]
    if not registered_tools:
        print("WARNING: ToolRegistry is empty after imports!")


# ============================================
# Authenticated HTTP Client Fixtures (for E2E tests)
# ============================================

@pytest.fixture(scope="module")
def api_base_url() -> str:
    """API server base URL from environment or default."""
    if settings is not None:
        host = getattr(settings, 'server_host', '127.0.0.1')
        port = getattr(settings, 'server_port', 8000)
        return f"http://{host}:{port}"
    return os.getenv("OLAV_SERVER_URL", "http://127.0.0.1:8000")


@pytest.fixture(scope="module")
def api_token() -> str:
    """API token for authenticated requests.

    In QuickTest mode (AUTH_DISABLED=true), returns empty string.
    In Production mode, reads from OLAV_API_TOKEN environment variable.
    """
    auth_disabled = os.getenv("AUTH_DISABLED", "false").lower() in ("true", "1", "yes")
    if auth_disabled:
        return ""
    return os.getenv("OLAV_API_TOKEN", "")


@pytest.fixture
def auth_headers(api_token: str) -> dict:
    """Authorization headers for API requests.

    Returns empty dict if auth is disabled (QuickTest mode).
    """
    if not api_token:
        return {}
    return {"Authorization": f"Bearer {api_token}"}


def pytest_configure(config):
    """Pytest hook called after command line options have been parsed.

    Pre-import tool modules to ensure ToolRegistry is populated BEFORE
    any tests run. This solves the state pollution issue where tests
    run before tools are registered.
    """

    tool_modules = [
        "olav.tools.suzieq_tool",
        "olav.tools.netbox_tool",
        "olav.tools.nornir_tool",
        "olav.tools.opensearch_tool",
    ]

    for module_name in tool_modules:
        try:
            importlib.import_module(module_name)
        except Exception as e:
            print(f"pytest_configure: Failed to import {module_name}: {e}")
