"""
Schema-Aware Field Mapper for Cross-System Data Synchronization.

This module implements dynamic field mapping between SuzieQ/OpenConfig and NetBox
using LLM-based schema discovery instead of hardcoded mapping dictionaries.

Architecture:
1. SchemaMapper discovers source/target schemas via *_schema_search tools
2. LLM generates field mappings based on semantic understanding
3. Mappings are cached in Redis for performance
4. Fallback to simple heuristics if LLM unavailable
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from olav.core.llm import LLMFactory
from olav.core.prompt_manager import prompt_manager
from olav.tools.base import ToolRegistry

logger = logging.getLogger(__name__)


class TransformType(str, Enum):
    """Supported field transformation types."""

    DIRECT = "direct"  # No transformation needed
    BOOLEAN_FROM_UPDOWN = "boolean_from_updown"  # "up"/"down" → True/False
    SPEED_TO_KBPS = "speed_to_kbps"  # Convert speed to kbps
    TYPE_MAPPING = "type_mapping"  # Use type mapping table
    MAC_NORMALIZE = "mac_normalize"  # Normalize MAC address format
    CUSTOM = "custom"  # Custom transform (LLM provides logic)


class FieldMapping(BaseModel):
    """A single field mapping between source and target systems."""

    source_field: str = Field(description="Field name in source system")
    target_field: str = Field(description="Field name in target system")
    transform: TransformType = Field(default=TransformType.DIRECT)
    description: str = Field(default="")


class TypeMappingEntry(BaseModel):
    """A type value mapping (e.g., interface types)."""

    source_value: str = Field(description="Value in source system")
    target_value: str = Field(description="Value in target system")


class SchemaMappingResult(BaseModel):
    """Complete mapping result for an entity type."""

    entity_type: str
    source_system: str
    target_system: str
    field_mappings: list[FieldMapping] = Field(default_factory=list)
    type_mappings: dict[str, str] = Field(default_factory=dict)
    unmappable_fields: list[str] = Field(default_factory=list)
    cached: bool = Field(default=False)


@dataclass
class SchemaMapper:
    """
    Dynamic schema mapper using LLM for field discovery and mapping.

    Uses schema search tools to discover available fields in both source
    and target systems, then generates mappings using LLM reasoning.

    Example:
        mapper = SchemaMapper()
        mapping = await mapper.get_mapping("interface", "suzieq", "netbox")
        netbox_data = mapper.apply_mapping(suzieq_data, mapping)
    """

    # Default fallback mappings when LLM is unavailable
    DEFAULT_INTERFACE_TYPE_MAP: ClassVar[dict[str, str]] = {
        "loopback": "virtual",
        "vlan": "virtual",
        "svi": "virtual",
        "tunnel": "virtual",
        "gre": "virtual",
        "ethernet": "1000base-t",
        "gigabit": "1000base-t",
        "tengigabit": "10gbase-t",
        "fastethernet": "100base-tx",
        "lag": "lag",
        "bond": "lag",
        "port-channel": "lag",
        "bridge": "bridge",
    }

    DEFAULT_FIELD_MAPPINGS: ClassVar[dict[str, list[dict[str, str]]]] = {
        "interface": [
            {"source": "ifname", "target": "name", "transform": "direct"},
            {"source": "adminState", "target": "enabled", "transform": "boolean_from_updown"},
            {"source": "type", "target": "type", "transform": "type_mapping"},
            {"source": "mtu", "target": "mtu", "transform": "direct"},
            {"source": "speed", "target": "speed", "transform": "speed_to_kbps"},
            {"source": "description", "target": "description", "transform": "direct"},
            {"source": "macaddr", "target": "mac_address", "transform": "mac_normalize"},
        ],
    }

    _cache: dict[str, SchemaMappingResult] = field(default_factory=dict)
    use_llm: bool = True
    cache_ttl: int = 3600  # 1 hour

    async def get_mapping(
        self,
        entity_type: str,
        source_system: str = "suzieq",
        target_system: str = "netbox",
    ) -> SchemaMappingResult:
        """
        Get field mapping for an entity type between two systems.

        First checks cache, then tries LLM-based discovery, finally falls
        back to default mappings.

        Args:
            entity_type: Entity type (e.g., "interface", "device", "ip_address")
            source_system: Source system name (default: "suzieq")
            target_system: Target system name (default: "netbox")

        Returns:
            SchemaMappingResult with field and type mappings
        """
        cache_key = f"{source_system}:{target_system}:{entity_type}"

        # Check memory cache
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            cached.cached = True
            return cached

        # Try LLM-based discovery
        if self.use_llm:
            try:
                result = await self._discover_mapping_with_llm(
                    entity_type, source_system, target_system
                )
                if result:
                    self._cache[cache_key] = result
                    return result
            except Exception as e:
                logger.warning(f"LLM mapping discovery failed: {e}, using defaults")

        # Fallback to defaults (also cache the result)
        result = self._get_default_mapping(entity_type, source_system, target_system)
        self._cache[cache_key] = result
        return result

    async def _discover_mapping_with_llm(
        self,
        entity_type: str,
        source_system: str,
        target_system: str,
    ) -> SchemaMappingResult | None:
        """
        Use LLM to discover field mappings by querying schema search tools.

        This is the core "Schema-Aware" approach - instead of hardcoding,
        we let the LLM figure out the mappings by examining actual schemas.
        """
        try:
            # 1. Get source schema
            source_schema = await self._get_schema(source_system, entity_type)
            if not source_schema:
                logger.debug(f"No source schema found for {source_system}/{entity_type}")
                return None

            # 2. Get target schema
            target_schema = await self._get_schema(target_system, entity_type)
            if not target_schema:
                logger.debug(f"No target schema found for {target_system}/{entity_type}")
                return None

            # 3. Use LLM to generate mappings
            llm = LLMFactory.get_chat_model(json_mode=False)

            # Load prompt template
            try:
                prompt_template = prompt_manager.load_prompt("sync/schema_discovery")
                prompt = prompt_template.format(
                    source_system=source_system,
                    target_system=target_system,
                    entity_type=entity_type,
                )
            except Exception:
                # Fallback if prompt not found
                prompt = self._build_mapping_prompt(
                    entity_type, source_system, target_system, source_schema, target_schema
                )

            # Use structured output for reliable parsing
            llm_with_structure = llm.with_structured_output(SchemaMappingResult)
            result = await llm_with_structure.ainvoke(prompt)

            if isinstance(result, SchemaMappingResult):
                return result

            return None

        except Exception as e:
            logger.error(f"LLM mapping discovery error: {e}")
            return None

    async def _get_schema(self, system: str, entity_type: str) -> dict[str, Any] | None:
        """Get schema for a system/entity using schema search tools."""
        tool_name = f"{system}_schema_search"
        tool = ToolRegistry.get_tool(tool_name)

        if not tool:
            logger.debug(f"Schema search tool not found: {tool_name}")
            return None

        try:
            result = await tool.execute(query=entity_type)
            if result.success and result.data:
                return result.data
        except Exception as e:
            logger.warning(f"Schema search failed for {system}/{entity_type}: {e}")

        return None

    def _get_default_mapping(
        self,
        entity_type: str,
        source_system: str,
        target_system: str,
    ) -> SchemaMappingResult:
        """Get default hardcoded mapping as fallback."""
        field_mappings = []
        type_mappings = {}

        if entity_type == "interface":
            for fm in self.DEFAULT_FIELD_MAPPINGS.get("interface", []):
                field_mappings.append(
                    FieldMapping(
                        source_field=fm["source"],
                        target_field=fm["target"],
                        transform=TransformType(fm["transform"]),
                    )
                )
            type_mappings = self.DEFAULT_INTERFACE_TYPE_MAP.copy()

        return SchemaMappingResult(
            entity_type=entity_type,
            source_system=source_system,
            target_system=target_system,
            field_mappings=field_mappings,
            type_mappings=type_mappings,
            cached=False,
        )

    def _build_mapping_prompt(
        self,
        entity_type: str,
        source_system: str,
        target_system: str,
        source_schema: dict[str, Any],
        target_schema: dict[str, Any],
    ) -> str:
        """Build a mapping prompt when template is not available."""
        return f"""
        Analyze these schemas and generate field mappings for {entity_type}.

        Source System: {source_system}
        Source Schema: {json.dumps(source_schema, indent=2)}

        Target System: {target_system}
        Target Schema: {json.dumps(target_schema, indent=2)}

        Generate mappings that:
        1. Match semantically equivalent fields
        2. Identify necessary transforms (boolean, speed units, type values)
        3. Note unmappable fields

        Return a SchemaMappingResult with field_mappings and type_mappings.
        """

    def apply_mapping(
        self,
        source_data: dict[str, Any],
        mapping: SchemaMappingResult,
    ) -> dict[str, Any]:
        """
        Apply a mapping to transform source data to target format.

        Args:
            source_data: Data from source system
            mapping: Mapping rules from get_mapping()

        Returns:
            Transformed data suitable for target system
        """
        result = {}

        for fm in mapping.field_mappings:
            source_value = source_data.get(fm.source_field)
            if source_value is None:
                continue

            target_value = self._apply_transform(
                source_value,
                fm.transform,
                mapping.type_mappings,
            )

            if target_value is not None:
                result[fm.target_field] = target_value

        return result

    def _apply_transform(
        self,
        value: Any,
        transform: TransformType,
        type_mappings: dict[str, str],
    ) -> Any:
        """Apply a single field transformation."""
        if transform == TransformType.DIRECT:
            return value

        if transform == TransformType.BOOLEAN_FROM_UPDOWN:
            if isinstance(value, str):
                return value.lower() == "up"
            return bool(value)

        if transform == TransformType.SPEED_TO_KBPS:
            return self._normalize_speed(value)

        if transform == TransformType.TYPE_MAPPING:
            if isinstance(value, str):
                # Try exact match first
                if value.lower() in type_mappings:
                    return type_mappings[value.lower()]
                # Try prefix match
                for pattern, mapped in type_mappings.items():
                    if pattern in value.lower():
                        return mapped
            return "other"

        if transform == TransformType.MAC_NORMALIZE:
            return self._normalize_mac(value)

        return value

    def _normalize_speed(self, speed: int | str | None) -> int | None:
        """Normalize speed to kbps for NetBox."""
        if speed is None:
            return None

        try:
            speed_int = int(speed)
        except (ValueError, TypeError):
            return None

        if speed_int <= 0:
            return None

        # Heuristic based on magnitude
        if speed_int < 1000:
            return speed_int * 1_000_000  # Gbps to kbps
        elif speed_int < 1_000_000:
            return speed_int * 1000  # Mbps to kbps
        elif speed_int < 1_000_000_000:
            return speed_int  # Already kbps
        else:
            return speed_int // 1000  # bps to kbps

    def _normalize_mac(self, mac: str | None) -> str | None:
        """Normalize MAC address to NetBox format (AA:BB:CC:DD:EE:FF)."""
        if not mac:
            return None

        # Remove all separators
        mac_clean = mac.replace(":", "").replace("-", "").replace(".", "").upper()

        if len(mac_clean) != 12:
            return None

        # Format as AA:BB:CC:DD:EE:FF
        return ":".join(mac_clean[i : i + 2] for i in range(0, 12, 2))

    def map_interface_type(self, sq_type: str | None, ifname: str | None = None) -> str:
        """
        Quick interface type mapping using defaults.

        This is a convenience method for the common case of mapping
        SuzieQ interface types to NetBox. For full schema-aware mapping,
        use get_mapping() + apply_mapping().

        Args:
            sq_type: SuzieQ interface type
            ifname: Interface name (for additional hints)

        Returns:
            NetBox interface type slug
        """
        if not sq_type and not ifname:
            return "other"

        # Check type first
        if sq_type:
            sq_lower = sq_type.lower()
            for pattern, netbox_type in self.DEFAULT_INTERFACE_TYPE_MAP.items():
                if pattern in sq_lower:
                    return netbox_type

        # Check interface name as fallback
        if ifname:
            ifname_lower = ifname.lower()
            if "loopback" in ifname_lower or ifname_lower.startswith("lo"):
                return "virtual"
            if "vlan" in ifname_lower:
                return "virtual"
            if "tunnel" in ifname_lower or "gre" in ifname_lower:
                return "virtual"
            if "gigabit" in ifname_lower or "ge-" in ifname_lower or ifname_lower.startswith("gi"):
                return "1000base-t"
            if "ethernet" in ifname_lower or ifname_lower.startswith("eth"):
                return "1000base-t"

        return "other"


# Module-level singleton
_schema_mapper: SchemaMapper | None = None


def get_schema_mapper() -> SchemaMapper:
    """Get or create the global SchemaMapper instance."""
    global _schema_mapper
    if _schema_mapper is None:
        _schema_mapper = SchemaMapper()
    return _schema_mapper
