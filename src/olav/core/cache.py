"""Redis-based distributed caching module.

Provides unified cache abstraction with Redis backend for:
- SchemaLoader schema caching (replace in-memory dict)
- Session state caching
- Episodic memory caching

Features:
- TTL support with automatic expiration
- JSON serialization for complex objects (including numpy types)
- Async operations using redis-py asyncio
- Graceful fallback to no-op cache if Redis unavailable
- Key namespacing to prevent collisions
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Literal

import numpy as np

# Lazy import to avoid circular imports and allow mocking in tests
if TYPE_CHECKING:
    from olav.core.settings import EnvSettings

logger = logging.getLogger(__name__)


class NumpyEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles numpy types."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (np.integer, np.int64)):
            return int(obj)
        if isinstance(obj, (np.floating, np.float64)):
            return float(obj)
        if isinstance(obj, np.bool_):
            return bool(obj)
        return super().default(obj)


def safe_json_dumps(obj: Any, **kwargs: Any) -> str:
    """JSON serialize with numpy type support.

    Convenience function for serializing objects that may contain numpy types.
    Commonly used for tool output serialization before LLM formatting.

    Args:
        obj: Object to serialize
        **kwargs: Additional kwargs passed to json.dumps (e.g., indent, sort_keys)

    Returns:
        JSON string
    """
    return json.dumps(obj, cls=NumpyEncoder, **kwargs)


def _get_settings() -> EnvSettings:
    """Get settings lazily to allow mocking in tests."""
    from olav.core.settings import settings

    return settings


class CacheBackend(ABC):
    """Abstract base class for cache backends.

    Defines the interface for all cache implementations.
    """

    @abstractmethod
    async def get(self, key: str) -> Any | None:
        """Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        ...

    @abstractmethod
    async def set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None,
    ) -> bool:
        """Set value in cache.

        Args:
            key: Cache key
            value: Value to cache (must be JSON-serializable)
            ttl: Time-to-live in seconds (None = use default)

        Returns:
            True if set successfully
        """
        ...

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete value from cache.

        Args:
            key: Cache key

        Returns:
            True if deleted, False if not found
        """
        ...

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if key exists in cache.

        Args:
            key: Cache key

        Returns:
            True if key exists and not expired
        """
        ...

    @abstractmethod
    async def clear_namespace(self, namespace: str) -> int:
        """Clear all keys in a namespace.

        Args:
            namespace: Key prefix to clear (e.g., "schema:" clears all schema cache)

        Returns:
            Number of keys deleted
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if cache backend is healthy.

        Returns:
            True if connected and operational
        """
        ...


class RedisCache(CacheBackend):
    """Redis-based cache implementation.

    Uses redis-py async client for distributed caching.
    Automatically serializes/deserializes JSON values.

    Key namespacing:
    - "schema:suzieq" -> SuzieQ schema cache
    - "schema:openconfig" -> OpenConfig schema cache
    - "session:xyz789" -> Session state cache

    Example:
        >>> cache = RedisCache("redis://localhost:6379")
        >>> await cache.set("schema:suzieq", schema_dict, ttl=3600)
        >>> schema = await cache.get("schema:suzieq")
    """

    def __init__(
        self,
        redis_url: str,
        default_ttl: int = 3600,
        key_prefix: str = "olav:",
    ) -> None:
        """Initialize Redis cache.

        Args:
            redis_url: Redis connection URL (e.g., "redis://localhost:6379")
            default_ttl: Default TTL in seconds (default: 3600 = 1 hour)
            key_prefix: Global key prefix for namespacing (default: "olav:")
        """
        self._redis_url = redis_url
        self._default_ttl = default_ttl
        self._key_prefix = key_prefix
        self._client: Any | None = None  # Lazy-loaded redis.asyncio.Redis
        self._connected = False

    async def _get_client(self) -> Any:
        """Get or create Redis client.

        Returns:
            Redis async client

        Raises:
            ConnectionError: If Redis connection fails
        """
        if self._client is None:
            try:
                import redis.asyncio as redis_async

                self._client = redis_async.from_url(
                    self._redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                )
                # Test connection
                await self._client.ping()
                self._connected = True
                logger.info(f"Redis cache connected: {self._redis_url}")
            except ImportError as e:
                logger.error("redis package not installed. Run: uv add redis")
                msg = "redis package not available"
                raise ConnectionError(msg) from e
            except Exception as e:
                logger.error(f"Redis connection failed: {e}")
                self._connected = False
                msg = f"Cannot connect to Redis: {e}"
                raise ConnectionError(msg) from e

        return self._client

    def _make_key(self, key: str) -> str:
        """Create full cache key with prefix.

        Args:
            key: User-provided key

        Returns:
            Full key with prefix (e.g., "olav:schema:suzieq")
        """
        return f"{self._key_prefix}{key}"

    def _serialize(self, value: Any) -> str:
        """Serialize value to JSON string.

        Handles numpy types (ndarray, int64, float64, bool_) via NumpyEncoder.

        Args:
            value: Value to serialize

        Returns:
            JSON string
        """
        return json.dumps(value, ensure_ascii=False, cls=NumpyEncoder)

    def _deserialize(self, data: str | None) -> Any | None:
        """Deserialize JSON string to value.

        Args:
            data: JSON string or None

        Returns:
            Deserialized value or None
        """
        if data is None:
            return None
        try:
            return json.loads(data)
        except json.JSONDecodeError as e:
            logger.warning(f"Cache deserialization failed: {e}")
            return None

    async def get(self, key: str) -> Any | None:
        """Get value from Redis cache.

        Args:
            key: Cache key (without prefix)

        Returns:
            Cached value or None if not found/expired
        """
        try:
            client = await self._get_client()
            full_key = self._make_key(key)
            data = await client.get(full_key)
            value = self._deserialize(data)

            if value is not None:
                logger.debug(f"Cache HIT: {key}")
            else:
                logger.debug(f"Cache MISS: {key}")

            return value
        except ConnectionError:
            logger.warning(f"Redis unavailable, cache MISS: {key}")
            return None
        except Exception as e:
            logger.error(f"Cache get error for {key}: {e}")
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None,
    ) -> bool:
        """Set value in Redis cache.

        Args:
            key: Cache key (without prefix)
            value: Value to cache (must be JSON-serializable)
            ttl: Time-to-live in seconds (None = use default)

        Returns:
            True if set successfully
        """
        try:
            client = await self._get_client()
            full_key = self._make_key(key)
            data = self._serialize(value)
            expire = ttl if ttl is not None else self._default_ttl

            await client.set(full_key, data, ex=expire)
            logger.debug(f"Cache SET: {key} (TTL: {expire}s)")
            return True
        except ConnectionError:
            logger.warning(f"Redis unavailable, cache SET skipped: {key}")
            return False
        except Exception as e:
            logger.error(f"Cache set error for {key}: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Delete value from Redis cache.

        Args:
            key: Cache key (without prefix)

        Returns:
            True if deleted, False if not found
        """
        try:
            client = await self._get_client()
            full_key = self._make_key(key)
            deleted = await client.delete(full_key)

            if deleted:
                logger.debug(f"Cache DELETE: {key}")
            return deleted > 0
        except ConnectionError:
            logger.warning(f"Redis unavailable, cache DELETE skipped: {key}")
            return False
        except Exception as e:
            logger.error(f"Cache delete error for {key}: {e}")
            return False

    async def exists(self, key: str) -> bool:
        """Check if key exists in Redis cache.

        Args:
            key: Cache key (without prefix)

        Returns:
            True if key exists and not expired
        """
        try:
            client = await self._get_client()
            full_key = self._make_key(key)
            return await client.exists(full_key) > 0
        except ConnectionError:
            return False
        except Exception as e:
            logger.error(f"Cache exists error for {key}: {e}")
            return False

    async def clear_namespace(self, namespace: str) -> int:
        """Clear all keys matching namespace pattern.

        Args:
            namespace: Key prefix to clear (e.g., "schema:" clears "olav:schema:*")

        Returns:
            Number of keys deleted
        """
        try:
            client = await self._get_client()
            pattern = f"{self._key_prefix}{namespace}*"

            # Use SCAN to find keys (safer than KEYS for production)
            deleted_count = 0
            cursor = 0
            while True:
                cursor, keys = await client.scan(cursor, match=pattern, count=100)
                if keys:
                    deleted_count += await client.delete(*keys)
                if cursor == 0:
                    break

            logger.info(f"Cache CLEAR namespace '{namespace}': {deleted_count} keys deleted")
            return deleted_count
        except ConnectionError:
            logger.warning(f"Redis unavailable, namespace clear skipped: {namespace}")
            return 0
        except Exception as e:
            logger.error(f"Cache clear namespace error for {namespace}: {e}")
            return 0

    async def health_check(self) -> bool:
        """Check Redis connection health.

        Returns:
            True if connected and operational
        """
        try:
            client = await self._get_client()
            await client.ping()
            return True
        except Exception as e:
            logger.debug(f"Redis health check failed: {e}")
            return False

    async def close(self) -> None:
        """Close Redis connection."""
        if self._client:
            await self._client.close()
            self._client = None
            self._connected = False
            logger.info("Redis cache connection closed")


class NoOpCache(CacheBackend):
    """No-operation cache backend for testing or when Redis unavailable.

    All operations succeed but don't persist data.
    Useful as fallback when Redis is not configured.

    Example:
        >>> cache = NoOpCache()
        >>> await cache.set("key", "value")  # Returns True but doesn't persist
        >>> await cache.get("key")  # Returns None
    """

    async def get(self, key: str) -> Any | None:
        """Always returns None (no persistence)."""
        logger.debug(f"NoOpCache GET: {key} (no-op)")
        return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None,
    ) -> bool:
        """Always returns True (no persistence)."""
        logger.debug(f"NoOpCache SET: {key} (no-op)")
        return True

    async def delete(self, key: str) -> bool:
        """Always returns False (nothing to delete)."""
        logger.debug(f"NoOpCache DELETE: {key} (no-op)")
        return False

    async def exists(self, key: str) -> bool:
        """Always returns False (no persistence)."""
        return False

    async def clear_namespace(self, namespace: str) -> int:
        """Always returns 0 (nothing to clear)."""
        logger.debug(f"NoOpCache CLEAR: {namespace} (no-op)")
        return 0

    async def health_check(self) -> bool:
        """Always returns True (always healthy)."""
        return True


# Cache namespaces (for type safety and documentation)
CacheNamespace = Literal["schema:", "session:", "memory:"]


class CacheManager:
    """High-level cache manager with namespace support.

    Provides type-safe caching operations with automatic namespace prefixing.

    Namespaces:
    - schema: Schema caching (SuzieQ, OpenConfig)
    - session: Session state caching
    - memory: Episodic memory caching

    Example:
        >>> manager = CacheManager(RedisCache("redis://localhost:6379"))
        >>> await manager.set_schema("suzieq", schema_dict)
        >>> schema = await manager.get_schema("suzieq")
    """

    def __init__(
        self,
        backend: CacheBackend,
        default_ttls: dict[CacheNamespace, int] | None = None,
    ) -> None:
        """Initialize cache manager.

        Args:
            backend: Cache backend implementation
            default_ttls: Namespace-specific default TTLs (optional)
        """
        self.backend = backend
        self._default_ttls: dict[CacheNamespace, int] = {
            "schema:": 3600,  # 1 hour for schemas
            "session:": 1800,  # 30 minutes for sessions
            "memory:": 7200,  # 2 hours for episodic memory
        }
        if default_ttls:
            self._default_ttls.update(default_ttls)

    def _make_namespaced_key(self, namespace: CacheNamespace, key: str) -> str:
        """Create namespaced key.

        Args:
            namespace: Cache namespace
            key: Key within namespace

        Returns:
            Namespaced key (e.g., "schema:suzieq")
        """
        return f"{namespace}{key}"

    # Schema caching methods
    async def get_schema(self, schema_type: str) -> dict[str, Any] | None:
        """Get cached schema.

        Args:
            schema_type: Schema type ("suzieq", "openconfig")

        Returns:
            Cached schema dict or None
        """
        key = self._make_namespaced_key("schema:", schema_type)
        return await self.backend.get(key)

    async def set_schema(
        self,
        schema_type: str,
        schema: dict[str, Any],
        ttl: int | None = None,
    ) -> bool:
        """Cache schema.

        Args:
            schema_type: Schema type ("suzieq", "openconfig")
            schema: Schema dictionary
            ttl: TTL in seconds (None = use default)

        Returns:
            True if cached successfully
        """
        key = self._make_namespaced_key("schema:", schema_type)
        ttl = ttl or self._default_ttls["schema:"]
        return await self.backend.set(key, schema, ttl)

    async def invalidate_schema(self, schema_type: str) -> bool:
        """Invalidate cached schema.

        Args:
            schema_type: Schema type to invalidate

        Returns:
            True if invalidated
        """
        key = self._make_namespaced_key("schema:", schema_type)
        return await self.backend.delete(key)

    # Session state caching methods
    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Get cached session state.

        Args:
            session_id: Session identifier

        Returns:
            Session state or None
        """
        key = self._make_namespaced_key("session:", session_id)
        return await self.backend.get(key)

    async def set_session(
        self,
        session_id: str,
        state: dict[str, Any],
        ttl: int | None = None,
    ) -> bool:
        """Cache session state.

        Args:
            session_id: Session identifier
            state: Session state dict
            ttl: TTL in seconds (None = use default)

        Returns:
            True if cached successfully
        """
        key = self._make_namespaced_key("session:", session_id)
        ttl = ttl or self._default_ttls["session:"]
        return await self.backend.set(key, state, ttl)

    # Utility methods
    async def clear_all_schemas(self) -> int:
        """Clear all cached schemas.

        Returns:
            Number of schemas cleared
        """
        return await self.backend.clear_namespace("schema:")

    async def health_check(self) -> bool:
        """Check cache backend health.

        Returns:
            True if healthy
        """
        return await self.backend.health_check()


# Global cache instance (singleton pattern)
_cache_manager: CacheManager | None = None


def get_cache_manager() -> CacheManager:
    """Get global CacheManager singleton.

    Creates RedisCache from settings.redis_url if available,
    falls back to NoOpCache if Redis not configured.

    Returns:
        Global CacheManager instance
    """
    global _cache_manager

    if _cache_manager is None:
        settings = _get_settings()

        if settings.redis_url:
            try:
                backend = RedisCache(settings.redis_url)
                logger.info(f"Using Redis cache: {settings.redis_url}")
            except Exception as e:
                logger.warning(f"Redis unavailable ({e}), using NoOpCache")
                backend = NoOpCache()
        else:
            logger.info("Redis URL not configured, using NoOpCache")
            backend = NoOpCache()

        _cache_manager = CacheManager(backend)

    return _cache_manager


async def init_cache() -> CacheManager:
    """Initialize and verify cache connection.

    Call this at application startup to verify Redis connectivity.

    Returns:
        Initialized CacheManager

    Example:
        >>> cache = await init_cache()
        >>> if await cache.health_check():
        ...     print("Cache ready")
    """
    manager = get_cache_manager()

    healthy = await manager.health_check()
    if healthy:
        logger.info("✓ Cache backend healthy")
    else:
        logger.warning("✗ Cache backend unhealthy (using fallback)")

    return manager
