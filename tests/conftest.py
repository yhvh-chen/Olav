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
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SRC_PATH = os.path.join(PROJECT_ROOT, 'src')
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)
# Add project root for config.settings imports
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# If a top-level module file (olav.py) was imported before the package,
# remove it so the package directory `olav/` can be imported.
import importlib
if 'olav' in sys.modules and not hasattr(sys.modules['olav'], '__path__'):
    del sys.modules['olav']

# Safe/import-tolerant fallbacks to avoid hard failures in minimal test contexts
try:  # pragma: no cover - defensive import
    from olav.core.memory import OpenSearchMemory  # type: ignore
except Exception:  # pragma: no cover
    class OpenSearchMemory:  # type: ignore
        def __init__(self, url: str):  # minimal stub
            self.url = url

try:  # pragma: no cover - defensive import
    from olav.core.settings import EnvSettings  # type: ignore
except Exception:  # pragma: no cover
    class EnvSettings:  # type: ignore
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)


@pytest.fixture
def test_settings() -> EnvSettings:
    """Test settings with safe defaults (stub-compatible)."""
    return EnvSettings(
        llm_provider="openai",
        llm_api_key="test-key",
        postgres_uri="postgresql://olav:OlavPG123!@localhost:55432/olav",
        opensearch_url="http://localhost:9200",
        redis_url="redis://localhost:6379",
    )


@pytest.fixture
async def checkpointer() -> PostgresSaver:
    """Shared PostgreSQL checkpointer for tests."""
    conn_string = "postgresql://olav:OlavPG123!@localhost:55432/olav"
    with PostgresSaver.from_conn_string(conn_string) as saver:
        saver.setup()
        yield saver


@pytest.fixture
def opensearch_memory() -> OpenSearchMemory:
    """Mock OpenSearch memory instance (stub if import failed)."""
    return OpenSearchMemory(url="http://localhost:9200")


@pytest.fixture
def mock_suzieq_context():
    """Mock SuzieQ context for testing."""
    # TODO: Implement mock SuzieQ context
    pass
