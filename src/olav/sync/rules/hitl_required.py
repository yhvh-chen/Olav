"""
HITL (Human-in-the-Loop) required rules for NetBox updates.

These rules define which changes require human approval
before being applied to NetBox.
"""

from olav.core.prompt_manager import prompt_manager
from olav.sync.models import DiffResult, DiffSeverity, EntityType

# Fields that always require HITL approval
HITL_REQUIRED_RULES: dict[EntityType, set[str]] = {
    EntityType.INTERFACE: {
        "enabled",
        "mode",
        "tagged_vlans",
        "untagged_vlan",
        "lag",
        "existence",  # Creating/deleting interfaces
    },
    EntityType.IP_ADDRESS: {
        "address",
        "assigned_object",
        "vrf",
        "existence",  # Creating/deleting IPs
    },
    EntityType.VLAN: {
        "vid",
        "name",
        "site",
        "existence",
    },
    EntityType.BGP_PEER: {
        "remote_as",
        "peer_address",
        "import_policy",
        "export_policy",
        "existence",
    },
    EntityType.DEVICE: {
        "site",
        "rack",
        "device_role",
        "platform",  # Platform changes are significant
        "existence",
    },
    EntityType.CABLE: {
        "a_terminations",
        "b_terminations",
        "existence",
    },
}


def requires_hitl_approval(diff: DiffResult) -> bool:
    """
    Check if a diff requires HITL approval.

    Args:
        diff: The difference to check

    Returns:
        True if HITL approval is required
    """
    # Critical severity always requires HITL
    if diff.severity == DiffSeverity.CRITICAL:
        return True

    # Check entity-specific rules
    entity_rules = HITL_REQUIRED_RULES.get(diff.entity_type, set())
    field_name = diff.field.split(".")[-1]

    return field_name in entity_rules


def get_hitl_prompt(diff: DiffResult) -> str:
    """
    Generate a human-readable prompt for HITL approval.

    Args:
        diff: The difference requiring approval

    Returns:
        Formatted prompt string
    """
    severity_emoji = {
        DiffSeverity.INFO: "ℹ️",
        DiffSeverity.WARNING: "⚠️",
        DiffSeverity.CRITICAL: "🔴",
    }

    emoji = severity_emoji.get(diff.severity, "")

    # Build additional context section
    additional_context = ""
    if diff.additional_context:
        additional_context = "\nAdditional Context:\n"
        for key, value in diff.additional_context.items():
            additional_context += f"  {key}: {value}\n"

    # Load prompt from config
    return prompt_manager.load_prompt(
        "sync",
        "hitl_prompt",
        emoji=emoji,
        device=diff.device,
        entity_type=diff.entity_type.value,
        field=diff.field,
        severity=diff.severity.value,
        netbox_value=diff.netbox_value,
        network_value=diff.network_value,
        source=diff.source.value,
        additional_context=additional_context,
    )


def get_hitl_summary(diffs: list[DiffResult]) -> str:
    """
    Generate a summary of all HITL-required changes.

    Args:
        diffs: List of differences requiring HITL

    Returns:
        Formatted summary string
    """
    if not diffs:
        return "No changes require HITL approval."

    lines = [
        "# HITL Approval Summary",
        f"Total changes requiring approval: {len(diffs)}",
        "",
        "| # | Device | Type | Field | Current | Proposed | Severity |",
        "|---|--------|------|-------|---------|----------|----------|",
    ]

    for i, diff in enumerate(diffs, 1):
        lines.append(
            f"| {i} | {diff.device} | {diff.entity_type.value} | "
            f"{diff.field} | {diff.netbox_value} | {diff.network_value} | "
            f"{diff.severity.value} |"
        )

    return "\n".join(lines)
