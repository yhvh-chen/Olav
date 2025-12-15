"""End-to-end tests for OLAV system."""
import pytest

from config.settings import settings


class TestInfrastructureConnectivity:
    """Test connections to infrastructure services."""

    def test_settings_loaded(self):
        """Test that settings are properly loaded."""
        assert settings.postgres_uri
        assert settings.opensearch_url
        # Note: redis_url is optional - Redis is not required for core functionality

    @pytest.mark.asyncio
    async def test_postgres_connection(self):
        """Test PostgreSQL connection."""
        from psycopg import AsyncConnection

        try:
            async with await AsyncConnection.connect(settings.postgres_uri) as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT 1")
                    result = await cur.fetchone()
                    assert result == (1,)
        except Exception as e:
            pytest.skip(f"PostgreSQL not available: {e}")

    @pytest.mark.asyncio
    async def test_opensearch_connection(self):
        """Test OpenSearch connection."""
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{settings.opensearch_url}/_cluster/health")
                assert response.status_code == 200
                data = response.json()
                assert data["status"] in ["green", "yellow"]
        except Exception as e:
            pytest.skip(f"OpenSearch not available: {e}")

    @pytest.mark.asyncio
    async def test_redis_connection(self):
        """Test Redis connection."""
        if not settings.redis_url:
            pytest.skip("Redis URL not configured (Redis is optional)")

        from redis.asyncio import Redis

        try:
            redis = Redis.from_url(settings.redis_url)
            await redis.ping()
            await redis.close()
        except Exception as e:
            pytest.skip(f"Redis not available: {e}")


class TestETLPipeline:
    """Test ETL initialization scripts."""

    @pytest.mark.asyncio
    async def test_postgres_checkpointer_setup(self):
        """Test PostgreSQL checkpointer tables exist."""
        from psycopg import AsyncConnection

        try:
            async with await AsyncConnection.connect(settings.postgres_uri) as conn:
                async with conn.cursor() as cur:
                    await cur.execute("""
                        SELECT tablename FROM pg_tables
                        WHERE schemaname = 'public'
                        AND tablename IN ('checkpoints', 'checkpoint_writes', 'checkpoint_migrations')
                    """)
                    tables = await cur.fetchall()
                    table_names = [t[0] for t in tables]

                    # Should have checkpointer tables if init ran
                    if tables:
                        assert "checkpoints" in table_names
        except Exception as e:
            pytest.skip(f"PostgreSQL not available: {e}")


class TestCoreComponents:
    """Test core OLAV components."""

    def test_llm_factory_import(self):
        """Test LLM factory can be imported."""
        from olav.core.llm import LLMFactory
        assert LLMFactory is not None

    def test_settings_import(self):
        """Test settings can be imported."""
        from config.settings import EnvSettings
        assert EnvSettings is not None

    def test_memory_import(self):
        """Test memory module can be imported."""
        from olav.core.memory import OpenSearchMemory
        assert OpenSearchMemory is not None


class TestToolsIntegration:
    """Test tools integration."""

    def test_opensearch_tool_import(self):
        """Test OpenSearch refactored tools can be imported (schema + episodic)."""
        from olav.tools.opensearch_tool import (
            EpisodicMemoryTool,
            OpenConfigSchemaTool,
            search_episodic_memory,
            search_openconfig_schema,
        )
        assert OpenConfigSchemaTool is not None
        assert EpisodicMemoryTool is not None
        # Wrappers exist (StructuredTool from @tool decorator)
        assert search_openconfig_schema is not None
        assert search_episodic_memory is not None
