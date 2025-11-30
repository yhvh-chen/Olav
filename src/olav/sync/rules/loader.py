"""
Sync Rules Loader - Load sync rules from YAML configuration.

Replaces hardcoded AUTO_CORRECT_FIELDS and HITL_REQUIRED_FIELDS dictionaries
with configuration-driven rules.
"""

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from olav.sync.models import EntityType

logger = logging.getLogger(__name__)

# Default config path (project_root/config/rules/)
# From src/olav/sync/rules/loader.py: parent x5 = project_root
CONFIG_DIR = Path(__file__).parent.parent.parent.parent.parent / "config" / "rules"
SYNC_RULES_FILE = CONFIG_DIR / "sync_rules.yaml"
HITL_CONFIG_FILE = CONFIG_DIR / "hitl_config.yaml"
DEEP_DIVE_CONFIG_FILE = CONFIG_DIR / "deep_dive_config.yaml"


@lru_cache(maxsize=1)
def _load_sync_rules() -> dict[str, Any]:
    """Load sync rules from YAML file (cached)."""
    if not SYNC_RULES_FILE.exists():
        logger.warning(f"Sync rules file not found: {SYNC_RULES_FILE}, using defaults")
        return {}

    try:
        with open(SYNC_RULES_FILE, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.error(f"Failed to load sync rules: {e}")
        return {}


@lru_cache(maxsize=1)
def _load_hitl_config() -> dict[str, Any]:
    """Load HITL config from YAML file (cached)."""
    if not HITL_CONFIG_FILE.exists():
        logger.warning(f"HITL config file not found: {HITL_CONFIG_FILE}, using defaults")
        return {}

    try:
        with open(HITL_CONFIG_FILE, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.error(f"Failed to load HITL config: {e}")
        return {}


def get_auto_correct_fields(entity_type: EntityType | str) -> list[str]:
    """
    Get list of auto-correctable fields for an entity type.

    Args:
        entity_type: Entity type (EntityType enum or string)

    Returns:
        List of field names that can be auto-corrected
    """
    rules = _load_sync_rules()
    entity_key = entity_type.value if isinstance(entity_type, EntityType) else entity_type

    auto_correct = rules.get("auto_correct_fields", {})
    return auto_correct.get(entity_key, [])


def get_hitl_required_fields(entity_type: EntityType | str) -> set[str]:
    """
    Get set of fields that require HITL approval.

    Args:
        entity_type: Entity type (EntityType enum or string)

    Returns:
        Set of field names that require HITL
    """
    rules = _load_sync_rules()
    entity_key = entity_type.value if isinstance(entity_type, EntityType) else entity_type

    hitl_required = rules.get("hitl_required_fields", {})
    return set(hitl_required.get(entity_key, []))


def is_auto_correctable(entity_type: EntityType | str, field_name: str) -> bool:
    """
    Check if a field can be auto-corrected.

    Args:
        entity_type: Entity type
        field_name: Field name to check

    Returns:
        True if field can be auto-corrected
    """
    auto_fields = get_auto_correct_fields(entity_type)
    # Handle nested fields like "interface.description"
    base_field = field_name.split(".")[-1]
    return base_field in auto_fields


def requires_hitl(entity_type: EntityType | str, field_name: str) -> bool:
    """
    Check if a field requires HITL approval.

    Args:
        entity_type: Entity type
        field_name: Field name to check

    Returns:
        True if field requires HITL
    """
    hitl_fields = get_hitl_required_fields(entity_type)
    base_field = field_name.split(".")[-1]
    return base_field in hitl_fields


def get_value_transform(transform_type: str, value: Any) -> Any:
    """
    Get transformed value using configured rules.

    Args:
        transform_type: Type of transformation (e.g., "status", "boolean")
        value: Value to transform

    Returns:
        Transformed value or original if no mapping
    """
    rules = _load_sync_rules()
    transforms = rules.get("value_transforms", {})
    type_transforms = transforms.get(transform_type, {})

    # Convert value to string for lookup
    value_str = str(value).lower() if value is not None else ""
    return type_transforms.get(value_str, value)


def get_field_severity(field_name: str) -> str:
    """
    Get severity level for a field.

    Args:
        field_name: Field name to check

    Returns:
        Severity level: "critical", "warning", or "info"
    """
    rules = _load_sync_rules()
    severity_rules = rules.get("severity_rules", {})

    base_field = field_name.split(".")[-1]

    if base_field in severity_rules.get("critical_fields", []):
        return "critical"
    if base_field in severity_rules.get("warning_fields", []):
        return "warning"
    return "info"


# HITL Config functions


def get_hitl_required_tools() -> set[str]:
    """Get set of tools that require HITL approval."""
    config = _load_hitl_config()
    return set(config.get("hitl_required_tools", []))


def get_safe_tools() -> set[str]:
    """Get set of tools that are always safe (read-only)."""
    config = _load_hitl_config()
    return set(config.get("safe_tools", []))


def is_tool_hitl_required(tool_name: str) -> bool:
    """
    Check if a tool requires HITL approval.

    Args:
        tool_name: Name of the tool

    Returns:
        True if tool requires HITL
    """
    hitl_tools = get_hitl_required_tools()
    safe_tools = get_safe_tools()

    if tool_name in safe_tools:
        return False
    if tool_name in hitl_tools:
        return True

    # Default: require HITL for unknown tools
    return True


def is_operation_hitl_required(operation: str) -> bool:
    """
    Check if an operation requires HITL based on operation name.

    Args:
        operation: Operation name (e.g., "edit-config", "get")

    Returns:
        True if operation requires HITL
    """
    config = _load_hitl_config()
    operation_rules = config.get("operation_rules", {})

    always_require = operation_rules.get("always_require", [])
    never_require = operation_rules.get("never_require", [])

    operation_lower = operation.lower()

    for pattern in never_require:
        if pattern in operation_lower:
            return False

    return any(pattern in operation_lower for pattern in always_require)


def get_approval_timeout() -> int:
    """Get HITL approval timeout in seconds."""
    config = _load_hitl_config()
    settings = config.get("approval_settings", {})
    return settings.get("timeout", 300)


def reload_rules() -> None:
    """Force reload of all rules (clear cache)."""
    _load_sync_rules.cache_clear()
    _load_hitl_config.cache_clear()
    _load_deep_dive_config.cache_clear()
    logger.info("Sync rules cache cleared, will reload on next access")


# ============================================
# Deep Dive Configuration Functions
# ============================================


@lru_cache(maxsize=1)
def _load_deep_dive_config() -> dict[str, Any]:
    """Load Deep Dive config from YAML file (cached)."""
    if not DEEP_DIVE_CONFIG_FILE.exists():
        logger.warning(f"Deep Dive config file not found: {DEEP_DIVE_CONFIG_FILE}, using defaults")
        return {}

    try:
        with open(DEEP_DIVE_CONFIG_FILE, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.error(f"Failed to load Deep Dive config: {e}")
        return {}


def get_osi_layer_tables() -> dict[str, list[str]]:
    """
    Get OSI layer to SuzieQ table mapping.

    Returns:
        Dictionary mapping layer names (L1-L4) to table lists
    """
    config = _load_deep_dive_config()
    tables = config.get("osi_layer_tables", {})

    # Fallback defaults if config empty
    if not tables:
        return {
            "L1": ["interfaces", "lldp"],
            "L2": ["macs", "vlan"],
            "L3": ["arpnd", "routes"],
            "L4": ["bgp", "ospfIf", "ospfNbr"],
        }

    return tables


def get_diagnostic_order() -> list[str]:
    """Get ordered list of OSI layers for funnel debugging."""
    config = _load_deep_dive_config()
    return config.get("diagnostic_order", ["L1", "L2", "L3", "L4"])


def get_layer_description(layer: str) -> str:
    """Get description for an OSI layer."""
    config = _load_deep_dive_config()
    descriptions = config.get("layer_descriptions", {})
    return descriptions.get(layer, f"{layer} layer diagnostics")


def get_layer_problem_indicators(layer: str) -> list[str]:
    """Get problem indicators for an OSI layer."""
    config = _load_deep_dive_config()
    indicators = config.get("layer_problem_indicators", {})
    return indicators.get(layer, [])


def get_deep_dive_trigger_patterns() -> list[str]:
    """Get patterns that trigger Deep Dive workflow."""
    config = _load_deep_dive_config()
    return config.get("trigger_patterns", ["deep dive", "troubleshoot", "排查"])


def get_recursion_limits() -> dict[str, int]:
    """Get recursion limits for Deep Dive workflow."""
    config = _load_deep_dive_config()
    limits = config.get("recursion_limits", {})
    return {
        "max_depth": limits.get("max_depth", 3),
        "max_devices": limits.get("max_devices", 30),
        "timeout_seconds": limits.get("timeout_seconds", 300),
    }
