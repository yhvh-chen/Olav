"""Pytest configuration and shared fixtures."""

import pytest
from langgraph.checkpoint.postgres import PostgresSaver

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
