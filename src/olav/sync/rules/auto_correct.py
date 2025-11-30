"""
Auto-correction rules for safe NetBox updates.

These rules define which fields can be automatically updated
without requiring human approval.
"""

from collections.abc import Callable
from typing import Any

from olav.sync.models import DiffResult, EntityType

# Auto-correct rules: entity_type -> field -> handler
AUTO_CORRECT_RULES: dict[EntityType, dict[str, Callable[[Any], Any]]] = {
    EntityType.INTERFACE: {
        "description": lambda v: str(v) if v else "",
        "mtu": lambda v: int(v) if v else None,
    },
    EntityType.DEVICE: {
        "serial": lambda v: str(v) if v else "",
        "software_version": lambda v: str(v) if v else "",
        # Note: platform changes are NOT auto-corrected
    },
    EntityType.IP_ADDRESS: {
        "status": lambda v: "active" if v in ("up", "active", True) else "deprecated",
        "dns_name": lambda v: str(v) if v else "",
    },
}


def is_safe_auto_correct(diff: DiffResult) -> bool:
    """
    Check if a diff can be safely auto-corrected.

    Args:
        diff: The difference to check

    Returns:
        True if safe to auto-correct
    """
    entity_rules = AUTO_CORRECT_RULES.get(diff.entity_type, {})
    field_name = diff.field.split(".")[-1]
    return field_name in entity_rules


def get_auto_correct_handler(
    diff: DiffResult,
) -> Callable[[Any], Any] | None:
    """
    Get the handler function for auto-correcting a field.

    Args:
        diff: The difference to get handler for

    Returns:
        Handler function or None if not auto-correctable
    """
    entity_rules = AUTO_CORRECT_RULES.get(diff.entity_type, {})
    field_name = diff.field.split(".")[-1]
    return entity_rules.get(field_name)


def transform_value_for_netbox(diff: DiffResult) -> Any:
    """
    Transform a network value for NetBox API format.

    Args:
        diff: The difference with network_value to transform

    Returns:
        Transformed value suitable for NetBox API
    """
    handler = get_auto_correct_handler(diff)
    if handler:
        return handler(diff.network_value)
    return diff.network_value
