"""Unit tests for Redis-based cache module.

Tests CacheBackend implementations:
- RedisCache: Redis backend (mocked)
- NoOpCache: No-operation backend
- CacheManager: High-level cache operations
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from olav.core.cache import (
    CacheBackend,
    CacheManager,
    NoOpCache,
    RedisCache,
    get_cache_manager,
    init_cache,
)


class TestNoOpCache:
    """Tests for NoOpCache implementation."""

    @pytest.fixture
    def cache(self) -> NoOpCache:
        """Create NoOpCache instance."""
        return NoOpCache()

    @pytest.mark.asyncio
    async def test_get_returns_none(self, cache: NoOpCache) -> None:
        """NoOpCache.get() always returns None."""
        result = await cache.get("any_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_returns_true(self, cache: NoOpCache) -> None:
        """NoOpCache.set() always returns True."""
        result = await cache.set("key", {"value": 123})
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_returns_false(self, cache: NoOpCache) -> None:
        """NoOpCache.delete() always returns False (nothing to delete)."""
        result = await cache.delete("key")
        assert result is False

    @pytest.mark.asyncio
    async def test_exists_returns_false(self, cache: NoOpCache) -> None:
        """NoOpCache.exists() always returns False."""
        result = await cache.exists("key")
        assert result is False

    @pytest.mark.asyncio
    async def test_clear_namespace_returns_zero(self, cache: NoOpCache) -> None:
        """NoOpCache.clear_namespace() always returns 0."""
        result = await cache.clear_namespace("schema:")
        assert result == 0

    @pytest.mark.asyncio
    async def test_health_check_returns_true(self, cache: NoOpCache) -> None:
        """NoOpCache.health_check() always returns True."""
        result = await cache.health_check()
        assert result is True


class TestRedisCache:
    """Tests for RedisCache implementation (mocked)."""

    @pytest.fixture
    def mock_redis_client(self) -> AsyncMock:
        """Create mock Redis async client."""
        client = AsyncMock()
        client.ping = AsyncMock(return_value=True)
        client.get = AsyncMock(return_value=None)
        client.set = AsyncMock(return_value=True)
        client.delete = AsyncMock(return_value=1)
        client.exists = AsyncMock(return_value=1)
        client.scan = AsyncMock(return_value=(0, []))
        client.close = AsyncMock()
        return client

    @pytest.fixture
    def cache(self, mock_redis_client: AsyncMock) -> RedisCache:
        """Create RedisCache with mocked client."""
        cache = RedisCache("redis://localhost:6379")
        cache._client = mock_redis_client
        cache._connected = True
        return cache

    @pytest.mark.asyncio
    async def test_get_hit(self, cache: RedisCache, mock_redis_client: AsyncMock) -> None:
        """Test cache get with hit."""
        mock_redis_client.get.return_value = '{"table": "bgp"}'
        
        result = await cache.get("schema:suzieq")
        
        assert result == {"table": "bgp"}
        mock_redis_client.get.assert_called_once_with("olav:schema:suzieq")

    @pytest.mark.asyncio
    async def test_get_miss(self, cache: RedisCache, mock_redis_client: AsyncMock) -> None:
        """Test cache get with miss."""
        mock_redis_client.get.return_value = None
        
        result = await cache.get("schema:nonexistent")
        
        assert result is None

    @pytest.mark.asyncio
    async def test_set_with_ttl(self, cache: RedisCache, mock_redis_client: AsyncMock) -> None:
        """Test cache set with custom TTL."""
        result = await cache.set("schema:suzieq", {"table": "bgp"}, ttl=600)
        
        assert result is True
        mock_redis_client.set.assert_called_once()
        call_args = mock_redis_client.set.call_args
        assert call_args[0][0] == "olav:schema:suzieq"
        assert call_args[1]["ex"] == 600

    @pytest.mark.asyncio
    async def test_set_with_default_ttl(self, cache: RedisCache, mock_redis_client: AsyncMock) -> None:
        """Test cache set with default TTL."""
        result = await cache.set("key", "value")
        
        call_args = mock_redis_client.set.call_args
        assert call_args[1]["ex"] == 3600  # Default TTL

    @pytest.mark.asyncio
    async def test_delete_existing_key(self, cache: RedisCache, mock_redis_client: AsyncMock) -> None:
        """Test deleting existing key."""
        mock_redis_client.delete.return_value = 1
        
        result = await cache.delete("schema:suzieq")
        
        assert result is True
        mock_redis_client.delete.assert_called_once_with("olav:schema:suzieq")

    @pytest.mark.asyncio
    async def test_delete_nonexistent_key(
        self,
        cache: RedisCache,
        mock_redis_client: AsyncMock,
    ) -> None:
        """Test deleting nonexistent key."""
        mock_redis_client.delete.return_value = 0
        
        result = await cache.delete("nonexistent")
        
        assert result is False

    @pytest.mark.asyncio
    async def test_exists_true(self, cache: RedisCache, mock_redis_client: AsyncMock) -> None:
        """Test exists returns True for existing key."""
        mock_redis_client.exists.return_value = 1
        
        result = await cache.exists("schema:suzieq")
        
        assert result is True

    @pytest.mark.asyncio
    async def test_exists_false(self, cache: RedisCache, mock_redis_client: AsyncMock) -> None:
        """Test exists returns False for missing key."""
        mock_redis_client.exists.return_value = 0
        
        result = await cache.exists("nonexistent")
        
        assert result is False

    @pytest.mark.asyncio
    async def test_clear_namespace(self, cache: RedisCache, mock_redis_client: AsyncMock) -> None:
        """Test clearing namespace with SCAN."""
        # Simulate SCAN returning keys then ending
        mock_redis_client.scan.side_effect = [
            (1, ["olav:schema:suzieq", "olav:schema:openconfig"]),
            (0, []),
        ]
        mock_redis_client.delete.return_value = 2
        
        result = await cache.clear_namespace("schema:")
        
        assert result == 2

    @pytest.mark.asyncio
    async def test_health_check_success(
        self,
        cache: RedisCache,
        mock_redis_client: AsyncMock,
    ) -> None:
        """Test health check when Redis is healthy."""
        mock_redis_client.ping.return_value = True
        
        result = await cache.health_check()
        
        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, cache: RedisCache, mock_redis_client: AsyncMock) -> None:
        """Test health check when Redis is down."""
        mock_redis_client.ping.side_effect = Exception("Connection refused")
        
        result = await cache.health_check()
        
        assert result is False

    @pytest.mark.asyncio
    async def test_close(self, cache: RedisCache, mock_redis_client: AsyncMock) -> None:
        """Test closing Redis connection."""
        await cache.close()
        
        mock_redis_client.close.assert_called_once()
        assert cache._client is None
        assert cache._connected is False

    def test_make_key_with_prefix(self, cache: RedisCache) -> None:
        """Test key prefix is applied correctly."""
        key = cache._make_key("schema:suzieq")
        
        assert key == "olav:schema:suzieq"

    def test_serialize_dict(self, cache: RedisCache) -> None:
        """Test JSON serialization."""
        data = {"table": "bgp", "fields": ["peer", "state"]}
        
        result = cache._serialize(data)
        
        assert json.loads(result) == data

    def test_deserialize_valid_json(self, cache: RedisCache) -> None:
        """Test JSON deserialization."""
        data = '{"table": "bgp"}'
        
        result = cache._deserialize(data)
        
        assert result == {"table": "bgp"}

    def test_deserialize_none(self, cache: RedisCache) -> None:
        """Test deserialize returns None for None input."""
        result = cache._deserialize(None)
        
        assert result is None

    def test_deserialize_invalid_json(self, cache: RedisCache) -> None:
        """Test deserialize handles invalid JSON gracefully."""
        result = cache._deserialize("not valid json")
        
        assert result is None


class TestCacheManager:
    """Tests for CacheManager high-level operations."""

    @pytest.fixture
    def mock_backend(self) -> AsyncMock:
        """Create mock cache backend."""
        backend = AsyncMock(spec=CacheBackend)
        backend.get = AsyncMock(return_value=None)
        backend.set = AsyncMock(return_value=True)
        backend.delete = AsyncMock(return_value=True)
        backend.exists = AsyncMock(return_value=False)
        backend.clear_namespace = AsyncMock(return_value=0)
        backend.health_check = AsyncMock(return_value=True)
        return backend

    @pytest.fixture
    def manager(self, mock_backend: AsyncMock) -> CacheManager:
        """Create CacheManager with mock backend."""
        return CacheManager(mock_backend)

    @pytest.mark.asyncio
    async def test_get_schema(self, manager: CacheManager, mock_backend: AsyncMock) -> None:
        """Test getting cached schema."""
        expected_schema = {"bgp": {"fields": ["peer"]}}
        mock_backend.get.return_value = expected_schema
        
        result = await manager.get_schema("suzieq")
        
        assert result == expected_schema
        mock_backend.get.assert_called_once_with("schema:suzieq")

    @pytest.mark.asyncio
    async def test_set_schema(self, manager: CacheManager, mock_backend: AsyncMock) -> None:
        """Test caching schema."""
        schema = {"bgp": {"fields": ["peer"]}}
        
        result = await manager.set_schema("suzieq", schema)
        
        assert result is True
        mock_backend.set.assert_called_once_with("schema:suzieq", schema, 3600)

    @pytest.mark.asyncio
    async def test_set_schema_custom_ttl(
        self,
        manager: CacheManager,
        mock_backend: AsyncMock,
    ) -> None:
        """Test caching schema with custom TTL."""
        schema = {"bgp": {"fields": ["peer"]}}
        
        await manager.set_schema("suzieq", schema, ttl=7200)
        
        mock_backend.set.assert_called_once_with("schema:suzieq", schema, 7200)

    @pytest.mark.asyncio
    async def test_invalidate_schema(
        self,
        manager: CacheManager,
        mock_backend: AsyncMock,
    ) -> None:
        """Test invalidating cached schema."""
        result = await manager.invalidate_schema("suzieq")
        
        assert result is True
        mock_backend.delete.assert_called_once_with("schema:suzieq")

    @pytest.mark.asyncio
    async def test_get_session(self, manager: CacheManager, mock_backend: AsyncMock) -> None:
        """Test getting cached session."""
        expected_session = {"user": "admin", "context": {}}
        mock_backend.get.return_value = expected_session
        
        result = await manager.get_session("session123")
        
        assert result == expected_session
        mock_backend.get.assert_called_once_with("session:session123")

    @pytest.mark.asyncio
    async def test_set_session(self, manager: CacheManager, mock_backend: AsyncMock) -> None:
        """Test caching session."""
        session = {"user": "admin"}
        
        result = await manager.set_session("session123", session)
        
        assert result is True
        mock_backend.set.assert_called_once_with("session:session123", session, 1800)

    @pytest.mark.asyncio
    async def test_clear_all_schemas(
        self,
        manager: CacheManager,
        mock_backend: AsyncMock,
    ) -> None:
        """Test clearing all schemas."""
        mock_backend.clear_namespace.return_value = 5
        
        result = await manager.clear_all_schemas()
        
        assert result == 5
        mock_backend.clear_namespace.assert_called_once_with("schema:")

    @pytest.mark.asyncio
    async def test_health_check(self, manager: CacheManager, mock_backend: AsyncMock) -> None:
        """Test health check delegation."""
        mock_backend.health_check.return_value = True
        
        result = await manager.health_check()
        
        assert result is True
        mock_backend.health_check.assert_called_once()

    def test_default_ttls(self, manager: CacheManager) -> None:
        """Test default TTL values."""
        assert manager._default_ttls["schema:"] == 3600
        assert manager._default_ttls["session:"] == 1800
        assert manager._default_ttls["memory:"] == 7200

    def test_custom_default_ttls(self, mock_backend: AsyncMock) -> None:
        """Test custom default TTL values."""
        custom_ttls = {"schema:": 7200, "session:": 3600}
        manager = CacheManager(mock_backend, default_ttls=custom_ttls)
        
        assert manager._default_ttls["schema:"] == 7200
        assert manager._default_ttls["session:"] == 3600
        # Original defaults preserved for non-overridden keys
        assert manager._default_ttls["memory:"] == 7200


class TestGlobalFunctions:
    """Tests for module-level functions."""

    @pytest.mark.asyncio
    async def test_get_cache_manager_creates_singleton(self) -> None:
        """Test get_cache_manager creates singleton."""
        # Clear global state
        import olav.core.cache as cache_module
        cache_module._cache_manager = None
        
        # Mock the _get_settings function
        mock_settings = MagicMock()
        mock_settings.redis_url = ""  # No Redis configured
        
        with patch.object(cache_module, "_get_settings", return_value=mock_settings):
            manager1 = get_cache_manager()
            manager2 = get_cache_manager()
            
            assert manager1 is manager2
            assert isinstance(manager1.backend, NoOpCache)
        
        # Reset for other tests
        cache_module._cache_manager = None

    @pytest.mark.asyncio
    async def test_get_cache_manager_with_redis_url(self) -> None:
        """Test get_cache_manager creates RedisCache when URL configured."""
        import olav.core.cache as cache_module
        cache_module._cache_manager = None
        
        mock_settings = MagicMock()
        mock_settings.redis_url = "redis://localhost:6379"
        
        with patch.object(cache_module, "_get_settings", return_value=mock_settings):
            manager = get_cache_manager()
            
            assert isinstance(manager.backend, RedisCache)
        
        # Reset for other tests
        cache_module._cache_manager = None

    @pytest.mark.asyncio
    async def test_init_cache_calls_health_check(self) -> None:
        """Test init_cache verifies connection."""
        import olav.core.cache as cache_module
        cache_module._cache_manager = None
        
        mock_settings = MagicMock()
        mock_settings.redis_url = ""
        
        with patch.object(cache_module, "_get_settings", return_value=mock_settings):
            manager = await init_cache()
            
            # NoOpCache always returns True for health_check
            healthy = await manager.health_check()
            assert healthy is True
        
        # Reset for other tests
        cache_module._cache_manager = None
