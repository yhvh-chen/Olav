"""Schema Loader - Dynamic schema loading from OpenSearch.

This module provides dynamic schema loading from OpenSearch indices,
replacing hardcoded schema dictionaries with runtime queries.

Supports both in-memory caching (for backward compatibility) and
distributed Redis caching (for production deployments).
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from olav.core.memory import OpenSearchMemory

if TYPE_CHECKING:
    from olav.core.cache import CacheManager

logger = logging.getLogger(__name__)


class SchemaLoader:
    """Load and cache schemas from OpenSearch indices.

    Provides dynamic schema discovery for Schema-Aware tools,
    eliminating hardcoded schema dictionaries.

    Features:
    - Lazy loading from OpenSearch
    - Redis distributed caching (preferred) or in-memory fallback
    - Fallback to minimal schema on errors
    - Support for multiple schema indices

    Cache Strategy:
    - If CacheManager provided: uses Redis for distributed caching
    - Otherwise: uses in-memory dict with TTL (legacy mode)
    """

    def __init__(
        self,
        memory: OpenSearchMemory | None = None,
        cache_ttl: int = 3600,
        cache_manager: CacheManager | None = None,
    ) -> None:
        """Initialize schema loader.

        Args:
            memory: OpenSearch memory instance (created if None)
            cache_ttl: Cache time-to-live in seconds (default: 3600 = 1 hour)
            cache_manager: Redis-backed CacheManager (optional, enables distributed caching)
        """
        self._memory = memory
        self._cache: dict[str, dict[str, Any]] = {}
        self._cache_timestamp: dict[str, float] = {}
        self._cache_ttl = cache_ttl
        self._cache_manager = cache_manager

    @property
    def memory(self) -> OpenSearchMemory:
        """Lazy-load OpenSearch memory."""
        if self._memory is None:
            self._memory = OpenSearchMemory()
        return self._memory

    @property
    def cache_manager(self) -> CacheManager | None:
        """Get cache manager (lazy-load from global if not provided)."""
        if self._cache_manager is None:
            try:
                from olav.core.cache import get_cache_manager

                self._cache_manager = get_cache_manager()
            except Exception as e:
                logger.debug(f"CacheManager not available: {e}")
        return self._cache_manager

    async def _get_from_cache(self, cache_key: str) -> dict[str, Any] | None:
        """Get schema from cache (Redis or memory).

        Args:
            cache_key: Cache key (e.g., "suzieq_schema")

        Returns:
            Cached schema or None
        """
        # Try Redis first
        if self.cache_manager:
            cached = await self.cache_manager.get_schema(cache_key)
            if cached:
                logger.debug(f"Redis cache HIT: {cache_key}")
                return cached

        # Fallback to in-memory cache
        if self._is_cache_valid(cache_key):
            logger.debug(f"Memory cache HIT: {cache_key}")
            return self._cache[cache_key]

        return None

    async def _set_to_cache(self, cache_key: str, schema: dict[str, Any]) -> None:
        """Set schema in cache (both Redis and memory).

        Args:
            cache_key: Cache key
            schema: Schema data to cache
        """
        # Update Redis
        if self.cache_manager:
            await self.cache_manager.set_schema(cache_key, schema, ttl=self._cache_ttl)
            logger.debug(f"Redis cache SET: {cache_key}")

        # Also update in-memory cache for performance
        self._cache[cache_key] = schema
        self._cache_timestamp[cache_key] = time.time()

    async def load_suzieq_schema(
        self,
        force_reload: bool = False,
    ) -> dict[str, dict[str, Any]]:
        """Load SuzieQ schema from OpenSearch suzieq-schema index.

        Returns schema dictionary mapping table names to their metadata:
        {
            "bgp": {
                "fields": ["namespace", "hostname", "peer", "state", ...],
                "description": "BGP protocol information",
                "methods": ["get", "summarize", "unique", "aver"]
            },
            ...
        }

        Args:
            force_reload: Force reload from OpenSearch, bypass cache

        Returns:
            Dictionary mapping table names to schema metadata
        """
        cache_key = "suzieq"

        # Check cache (Redis then memory)
        if not force_reload:
            cached = await self._get_from_cache(cache_key)
            if cached:
                return cached

        logger.info("Loading SuzieQ schema from OpenSearch...")

        try:
            # Query OpenSearch for all schemas
            results = await self.memory.search_schema(
                index="suzieq-schema",
                query={"match_all": {}},
                size=100,  # Should cover all SuzieQ tables
            )

            if not results:
                logger.warning("No schemas found in suzieq-schema index, using fallback")
                return self._get_fallback_suzieq_schema()

            # Convert to schema dictionary
            schema_dict = {}
            for doc in results:
                table_name = doc.get("table")
                if not table_name:
                    continue

                schema_dict[table_name] = {
                    "fields": doc.get("fields", []),
                    "description": doc.get("description", f"{table_name} table"),
                    "methods": doc.get("methods", ["get", "summarize"]),
                }

            # Update cache (Redis + memory)
            await self._set_to_cache(cache_key, schema_dict)

            logger.info(f"✓ Loaded {len(schema_dict)} SuzieQ table schemas from OpenSearch")
            return schema_dict

        except Exception as e:
            logger.error(f"Failed to load SuzieQ schema from OpenSearch: {e}")
            logger.warning("Falling back to minimal hardcoded schema")
            return self._get_fallback_suzieq_schema()

    async def load_openconfig_schema(
        self,
        force_reload: bool = False,
    ) -> list[dict[str, Any]]:
        """Load OpenConfig YANG schema from OpenSearch.

        Returns list of XPath entries with descriptions and examples.

        Args:
            force_reload: Force reload from OpenSearch, bypass cache

        Returns:
            List of XPath schema entries
        """
        cache_key = "openconfig"

        # Check cache (Redis then memory)
        if not force_reload:
            cached = await self._get_from_cache(cache_key)
            if cached:
                return cached

        logger.info("Loading OpenConfig schema from OpenSearch...")

        try:
            results = await self.memory.search_schema(
                index="openconfig-schema",
                query={"match_all": {}},
                size=1000,
            )

            # Update cache (Redis + memory)
            await self._set_to_cache(cache_key, results)

            logger.info(f"✓ Loaded {len(results)} OpenConfig XPath schemas")
            return results

        except Exception as e:
            logger.error(f"Failed to load OpenConfig schema: {e}")
            return []

    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cached schema is still valid.

        Args:
            cache_key: Cache key to check

        Returns:
            True if cache exists and not expired
        """
        if cache_key not in self._cache:
            return False

        age = time.time() - self._cache_timestamp.get(cache_key, 0)
        return age < self._cache_ttl

    def _get_fallback_suzieq_schema(self) -> dict[str, dict[str, Any]]:
        """Return minimal fallback schema if OpenSearch is unavailable.

        Contains only the most essential tables for basic functionality.
        Updated to match actual SuzieQ table names (ospfNbr, ospfIf).
        """
        logger.warning("Using minimal fallback SuzieQ schema (10 core tables)")
        return {
            "bgp": {
                "fields": [
                    "namespace",
                    "hostname",
                    "vrf",
                    "peer",
                    "asn",
                    "state",
                    "peerAsn",
                    "peerHostname",
                ],
                "description": "BGP protocol information",
                "methods": ["get", "summarize"],
            },
            "interfaces": {
                "fields": [
                    "namespace",
                    "hostname",
                    "ifname",
                    "state",
                    "adminState",
                    "mtu",
                    "speed",
                ],
                "description": "Network interface status",
                "methods": ["get", "summarize"],
            },
            "routes": {
                "fields": [
                    "namespace",
                    "hostname",
                    "vrf",
                    "prefix",
                    "nexthopIp",
                    "protocol",
                    "metric",
                ],
                "description": "Routing table entries",
                "methods": ["get", "summarize"],
            },
            "ospfNbr": {
                "fields": [
                    "namespace",
                    "hostname",
                    "vrf",
                    "ifname",
                    "area",
                    "state",
                    "peerRouterId",
                    "peerIP",
                ],
                "description": "OSPF neighbor information",
                "methods": ["get", "summarize"],
            },
            "ospfIf": {
                "fields": [
                    "namespace",
                    "hostname",
                    "vrf",
                    "ifname",
                    "area",
                    "state",
                    "networkType",
                    "cost",
                ],
                "description": "OSPF interface configuration",
                "methods": ["get", "summarize"],
            },
            "lldp": {
                "fields": ["namespace", "hostname", "ifname", "peerHostname", "peerIfname"],
                "description": "LLDP neighbor discovery",
                "methods": ["get", "summarize"],
            },
            "device": {
                "fields": ["namespace", "hostname", "model", "vendor", "version", "status"],
                "description": "Device hardware and software information",
                "methods": ["get", "summarize"],
            },
            "macs": {
                "fields": ["namespace", "hostname", "vlan", "macaddr", "oif"],
                "description": "MAC address table",
                "methods": ["get", "summarize"],
            },
            "arpnd": {
                "fields": ["namespace", "hostname", "ipAddress", "macaddr", "state"],
                "description": "ARP/ND table entries",
                "methods": ["get", "summarize"],
            },
            "vlan": {
                "fields": ["namespace", "hostname", "vlanName", "vlan", "state", "interfaces"],
                "description": "VLAN configuration",
                "methods": ["get", "summarize"],
            },
        }

    async def clear_cache(self) -> None:
        """Clear all cached schemas (Redis + memory)."""
        # Clear Redis cache
        if self.cache_manager:
            await self.cache_manager.clear_all_schemas()
            logger.info("Redis schema cache cleared")

        # Clear in-memory cache
        self._cache.clear()
        self._cache_timestamp.clear()
        logger.info("Memory schema cache cleared")

    async def get_key_fields(self, table: str) -> list[str]:
        """Get key fields for a SuzieQ table from schema.

        Queries the suzieq-schema-fields index for fields with is_key=true.
        Falls back to sensible defaults if schema query fails.

        Args:
            table: SuzieQ table name (e.g., "bgp", "interfaces")

        Returns:
            List of key field names for deduplication
        """
        cache_key = f"key_fields_{table}"

        # Check cache first
        cached = await self._get_from_cache(cache_key)
        if cached:
            cached_fields = cached.get("fields", ["hostname"])
            fallback = self._get_fallback_key_fields(table)
            # Safety: prefer table-specific fallback if cached fields are known to be insufficient.
            # This prevents collapsing multi-entity tables (e.g., interfaces) into too few rows.
            validated = self._validate_key_fields(table, cached_fields)
            if validated != cached_fields:
                await self._set_to_cache(cache_key, {"fields": validated})
                return validated

            # Extra safety: if cache only contains hostname but we have a better table-specific fallback,
            # prefer the fallback.
            if cached_fields == ["hostname"] and fallback != ["hostname"]:
                await self._set_to_cache(cache_key, {"fields": fallback})
                return fallback

            return cached_fields

        try:
            # Query OpenSearch for key fields
            results = await self.memory.search_schema(
                index="suzieq-schema-fields",
                query={"bool": {"must": [{"term": {"table": table}}, {"term": {"is_key": True}}]}},
                size=20,
            )

            key_fields = [doc.get("field") for doc in results if doc.get("field")]

            if not key_fields:
                # If schema index doesn't define keys for this table, use table-specific defaults.
                key_fields = self._get_fallback_key_fields(table)

            # Validate and harden key fields for tables where an incomplete keyset would collapse rows.
            key_fields = self._validate_key_fields(table, key_fields)

            # Cache the result
            await self._set_to_cache(cache_key, {"fields": key_fields})

            logger.debug(f"Key fields for {table}: {key_fields}")
            return key_fields

        except Exception as e:
            logger.warning(f"Failed to get key fields for {table}: {e}, using fallback")
            return self._get_fallback_key_fields(table)

    def _validate_key_fields(self, table: str, key_fields: list[str]) -> list[str]:
        """Validate/repair key fields for deduplication.

        Some schema sources can return a technically-valid but practically-insufficient keyset
        (e.g., missing 'ifname' for interfaces), which collapses multi-entity tables.
        """
        fallback = self._get_fallback_key_fields(table)

        # Interfaces must include ifname; otherwise dedup collapses to a handful of rows (e.g., by type).
        if table == "interfaces" and "ifname" not in key_fields:
            return fallback

        return key_fields

    def _get_fallback_key_fields(self, table: str) -> list[str]:
        """Return fallback key fields when OpenSearch is unavailable.

        Provides sensible defaults based on common SuzieQ table structures.
        """
        fallback_keys = {
            "bgp": ["hostname", "peer", "afi", "safi"],
            "interfaces": ["hostname", "ifname"],
            "routes": ["hostname", "vrf", "prefix"],
            "lldp": ["hostname", "ifname"],
            "device": ["hostname"],
            "ospfNbr": ["hostname", "vrf", "ifname", "peerRouterId"],
            "ospfIf": ["hostname", "vrf", "ifname"],
            "macs": ["hostname", "vlan", "macaddr"],
            "arpnd": ["hostname", "ipAddress"],
            "vlan": ["hostname", "vlan"],
        }
        return fallback_keys.get(table, ["hostname"])


# Global singleton instance for convenience
_global_loader: SchemaLoader | None = None


def get_schema_loader() -> SchemaLoader:
    """Get global SchemaLoader singleton.

    Creates SchemaLoader with auto-loaded CacheManager for Redis support.

    Returns:
        Global SchemaLoader instance
    """
    global _global_loader
    if _global_loader is None:
        _global_loader = SchemaLoader()
    return _global_loader
