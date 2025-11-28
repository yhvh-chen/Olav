"""
LLM-Driven Diff Engine - Let LLM compare NetBox and Network data directly.

This module replaces the complex Schema-Aware mapping system with a simpler
LLM-driven approach. The LLM directly compares JSON data from NetBox and
SuzieQ/network sources, understanding semantic equivalence automatically.

Benefits:
- Zero mapping maintenance
- Automatic adaptation to new NetBox plugins
- Handles abbreviations (GigabitEthernet0/0 = Gi0/0)
- Understands semantic equivalence (enabled=True ↔ adminState="up")

Usage:
    from olav.sync.llm_diff import LLMDiffEngine

    engine = LLMDiffEngine()
    diffs = await engine.compare(device="R1", netbox_data=nb, network_data=sq)
"""

import json
import logging
from typing import Any, Literal

from pydantic import BaseModel, Field

from olav.core.llm import LLMFactory

logger = logging.getLogger(__name__)


# ============ Pydantic Models for LLM Output Validation ============


class FieldDiff(BaseModel):
    """Single field difference identified by LLM."""

    field_name: str = Field(description="Name of the differing field")
    netbox_value: Any = Field(description="Value from NetBox")
    network_value: Any = Field(description="Value from network/SuzieQ")
    semantic_match: bool = Field(
        default=False,
        description="True if values are semantically equivalent despite different format",
    )
    severity: Literal["info", "warning", "critical"] = Field(
        default="info",
        description="Severity: info (cosmetic), warning (review), critical (action needed)",
    )
    explanation: str = Field(description="Brief explanation of the difference")


class EntityDiff(BaseModel):
    """Diff result for a single entity (interface, IP, VLAN, etc.)."""

    entity_type: str = Field(description="Type: interface, ip_address, vlan, device, etc.")
    identifier: str = Field(description="Entity identifier (interface name, IP, VLAN ID)")
    exists_in_netbox: bool = Field(default=True)
    exists_in_network: bool = Field(default=True)
    field_diffs: list[FieldDiff] = Field(default_factory=list)
    auto_correctable: bool = Field(
        default=False,
        description="Can this diff be auto-corrected without human approval",
    )


class ComparisonResult(BaseModel):
    """Complete comparison result from LLM."""

    device: str = Field(description="Device hostname")
    entity_diffs: list[EntityDiff] = Field(default_factory=list)
    summary: str = Field(description="Brief summary of findings")
    total_entities: int = Field(default=0)
    matched: int = Field(default=0)
    mismatched: int = Field(default=0)


# ============ LLM Diff Engine ============


COMPARISON_PROMPT = """You are a network engineer comparing data between NetBox (DCIM/IPAM) and actual network state.

**Task**: Compare the following two JSON objects and identify meaningful differences.

**NetBox Data** (Source of Truth - DCIM/IPAM):
```json
{netbox_json}
```

**Network Data** (Live state from SuzieQ/device):
```json
{network_json}
```

**Comparison Rules**:
1. **Interface Names**: "GigabitEthernet0/0" = "Gi0/0" = "ge-0/0/0" (consider equivalent)
2. **Admin State**: `enabled: true` ≈ `adminState: "up"`, `enabled: false` ≈ `adminState: "down"`
3. **Speed Units**: Be aware of kbps vs Mbps vs Gbps conversions
4. **MAC Address**: Normalize format (xx:xx:xx = xx-xx-xx = xxxx.xxxx)
5. **IP Address**: /32 suffix on host addresses may be implicit
6. **Empty vs Missing**: Empty string "" and null/missing are often equivalent
7. **Case**: Field names and string values may have different casing

**Severity Guidelines**:
- `info`: Cosmetic differences (formatting, case, empty vs null)
- `warning`: Should be reviewed but not urgent (description mismatch, stale data)
- `critical`: Operational impact (admin state mismatch, IP mismatch, missing critical interface)

**Auto-Correctable** (safe to sync without human approval):
- Description, comments, labels
- MTU (if network value is authoritative)
- Serial number, software version updates

**Requires Human Approval** (NOT auto-correctable):
- Admin state changes (enabled/disabled)
- IP address changes
- VLAN assignments
- Creating/deleting interfaces

Return your analysis as a structured ComparisonResult.
Focus on **meaningful** differences that require attention.
Ignore fields that are semantically equivalent or cosmetically different."""


class LLMDiffEngine:
    """
    LLM-driven diff engine that compares NetBox and network data.

    Uses structured output to ensure consistent, validated results.
    """

    def __init__(self, model: Any = None) -> None:
        """Initialize with optional LLM model."""
        self._model = model

    def _get_model(self) -> Any:
        """Get or create LLM with structured output."""
        if self._model is None:
            base_model = LLMFactory.get_chat_model()
            self._model = base_model.with_structured_output(ComparisonResult)
        return self._model

    async def compare(
        self,
        device: str,
        netbox_data: dict[str, Any],
        network_data: dict[str, Any],
    ) -> ComparisonResult:
        """
        Compare NetBox and network data using LLM.

        Args:
            device: Device hostname
            netbox_data: Data from NetBox API
            network_data: Data from SuzieQ/network

        Returns:
            ComparisonResult with structured diff information
        """
        model = self._get_model()

        # Format the prompt
        prompt = COMPARISON_PROMPT.format(
            netbox_json=json.dumps(netbox_data, indent=2, default=str),
            network_json=json.dumps(network_data, indent=2, default=str),
        )

        try:
            result = await model.ainvoke(prompt)

            # Ensure device is set
            if not result.device:
                result.device = device

            logger.info(
                f"LLM comparison for {device}: "
                f"{result.matched} matched, {result.mismatched} mismatched"
            )

            return result

        except Exception as e:
            logger.error(f"LLM comparison failed for {device}: {e}")
            # Return empty result on error
            return ComparisonResult(
                device=device,
                summary=f"Comparison failed: {e!s}",
                entity_diffs=[],
            )

    async def compare_interfaces(
        self,
        device: str,
        netbox_interfaces: list[dict[str, Any]],
        network_interfaces: list[dict[str, Any]],
    ) -> ComparisonResult:
        """
        Compare interface data between NetBox and network.

        Convenience method that structures data for comparison.
        """
        return await self.compare(
            device=device,
            netbox_data={"interfaces": netbox_interfaces},
            network_data={"interfaces": network_interfaces},
        )

    async def compare_ip_addresses(
        self,
        device: str,
        netbox_ips: list[dict[str, Any]],
        network_ips: list[dict[str, Any]],
    ) -> ComparisonResult:
        """Compare IP address data."""
        return await self.compare(
            device=device,
            netbox_data={"ip_addresses": netbox_ips},
            network_data={"ip_addresses": network_ips},
        )

    async def compare_entities(
        self,
        entity_type: str,
        device: str,
        netbox_data: dict[str, dict[str, Any]],
        network_data: dict[str, dict[str, Any]],
    ) -> list["SimpleDiff"]:
        """
        Compare entities and return a flat list of differences.

        This is the main interface used by DiffEngine.

        Args:
            entity_type: Type of entity (interface, ip_address, etc.)
            device: Device hostname
            netbox_data: Dict of entity_name -> entity_data from NetBox
            network_data: Dict of entity_name -> entity_data from network

        Returns:
            List of SimpleDiff objects for compatibility with DiffEngine
        """
        # Get full comparison result
        result = await self.compare(
            device=device,
            netbox_data={entity_type: netbox_data},
            network_data={entity_type: network_data},
        )

        # Convert to flat diff list
        diffs = []
        for entity in result.entity_diffs:
            # Handle existence differences
            if not entity.exists_in_netbox:
                diffs.append(
                    SimpleDiff(
                        field="existence",
                        netbox_value="missing",
                        network_value="present",
                        identifier=entity.identifier,
                        diff_type="missing_in_netbox",
                        reason=f"{entity.identifier} exists in network but not in NetBox",
                    )
                )
            elif not entity.exists_in_network:
                diffs.append(
                    SimpleDiff(
                        field="existence",
                        netbox_value="present",
                        network_value="missing",
                        identifier=entity.identifier,
                        diff_type="missing_in_network",
                        reason=f"{entity.identifier} exists in NetBox but not in network",
                    )
                )

            # Handle field differences
            for fd in entity.field_diffs:
                if fd.semantic_match:
                    continue  # Skip equivalent values
                diffs.append(
                    SimpleDiff(
                        field=f"{entity.identifier}.{fd.field_name}",
                        netbox_value=fd.netbox_value,
                        network_value=fd.network_value,
                        identifier=entity.identifier,
                        diff_type="field_mismatch",
                        reason=fd.explanation,
                    )
                )

        return diffs


class SimpleDiff(BaseModel):
    """Simple diff structure for DiffEngine compatibility."""

    field: str
    netbox_value: Any
    network_value: Any
    identifier: str | None = None
    diff_type: Literal["missing_in_netbox", "missing_in_network", "field_mismatch"] = (
        "field_mismatch"
    )
    reason: str | None = None


# ============ Conversion Helpers ============


def comparison_to_diffs(result: ComparisonResult) -> list[dict[str, Any]]:
    """
    Convert ComparisonResult to legacy DiffResult format for compatibility.

    This allows gradual migration from the old diff engine.
    """
    from olav.sync.models import DiffResult, DiffSeverity, DiffSource, EntityType

    diffs = []

    for entity in result.entity_diffs:
        # Map entity type
        entity_type_map = {
            "interface": EntityType.INTERFACE,
            "ip_address": EntityType.IP_ADDRESS,
            "vlan": EntityType.VLAN,
            "device": EntityType.DEVICE,
            "bgp_peer": EntityType.BGP_PEER,
        }
        entity_type = entity_type_map.get(entity.entity_type.lower(), EntityType.INTERFACE)

        # Handle existence differences
        if not entity.exists_in_netbox:
            diffs.append(
                DiffResult(
                    entity_type=entity_type,
                    device=result.device,
                    field="existence",
                    network_value="present",
                    netbox_value="missing",
                    severity=DiffSeverity.WARNING,
                    source=DiffSource.SUZIEQ,
                    auto_correctable=False,
                    identifier=entity.identifier,
                )
            )
        elif not entity.exists_in_network:
            diffs.append(
                DiffResult(
                    entity_type=entity_type,
                    device=result.device,
                    field="existence",
                    network_value="missing",
                    netbox_value="present",
                    severity=DiffSeverity.INFO,
                    source=DiffSource.SUZIEQ,
                    auto_correctable=False,
                    identifier=entity.identifier,
                )
            )

        # Handle field differences
        for field_diff in entity.field_diffs:
            if field_diff.semantic_match:
                continue  # Skip semantically equivalent values

            severity_map = {
                "info": DiffSeverity.INFO,
                "warning": DiffSeverity.WARNING,
                "critical": DiffSeverity.CRITICAL,
            }

            diffs.append(
                DiffResult(
                    entity_type=entity_type,
                    device=result.device,
                    field=f"{entity.identifier}.{field_diff.field_name}",
                    network_value=field_diff.network_value,
                    netbox_value=field_diff.netbox_value,
                    severity=severity_map.get(field_diff.severity, DiffSeverity.INFO),
                    source=DiffSource.SUZIEQ,
                    auto_correctable=entity.auto_correctable,
                    identifier=entity.identifier,
                    additional_context={"explanation": field_diff.explanation},
                )
            )

    return diffs
