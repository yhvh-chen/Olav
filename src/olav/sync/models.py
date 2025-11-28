"""
Data models for NetBox Bidirectional Sync.

Defines:
- DiffResult: Single difference between network and NetBox
- ReconciliationReport: Complete diff report across devices
- ReconcileAction/Result: Sync operation results
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class EntityType(str, Enum):
    """Types of entities that can be compared."""
    INTERFACE = "interface"
    IP_ADDRESS = "ip_address"
    VLAN = "vlan"
    BGP_PEER = "bgp_peer"
    DEVICE = "device"
    CABLE = "cable"
    ROUTE = "route"


class DiffSeverity(str, Enum):
    """Severity levels for differences."""
    INFO = "info"           # Informational only
    WARNING = "warning"     # Should be reviewed
    CRITICAL = "critical"   # Requires immediate attention


class DiffSource(str, Enum):
    """Source of network data."""
    SUZIEQ = "suzieq"
    OPENCONFIG = "openconfig"
    CLI = "cli"


class ReconcileAction(str, Enum):
    """Actions taken during reconciliation."""
    AUTO_CORRECTED = "auto_corrected"
    HITL_PENDING = "hitl_pending"
    HITL_APPROVED = "hitl_approved"
    HITL_REJECTED = "hitl_rejected"
    REPORT_ONLY = "report_only"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class DiffResult:
    """
    Single difference between network state and NetBox.
    
    Attributes:
        entity_type: Type of entity (interface, ip_address, etc.)
        device: Device hostname
        field: Specific field that differs
        network_value: Value from network (SuzieQ/CLI/OpenConfig)
        netbox_value: Value from NetBox API
        severity: How critical is this difference
        source: Where network data came from
        auto_correctable: Can this be auto-fixed without HITL
        netbox_id: NetBox object ID for updates (optional)
        netbox_endpoint: NetBox API endpoint for updates
        identifier: Entity identifier (interface name, IP address, etc.)
        additional_context: Extra context for decision making
    """
    entity_type: EntityType
    device: str
    field: str
    network_value: Any
    netbox_value: Any
    severity: DiffSeverity
    source: DiffSource
    auto_correctable: bool = False
    netbox_id: int | None = None
    netbox_endpoint: str | None = None
    identifier: str | None = None  # e.g., interface name "GigabitEthernet0/0"
    additional_context: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "entity_type": self.entity_type.value,
            "device": self.device,
            "field": self.field,
            "network_value": self.network_value,
            "netbox_value": self.netbox_value,
            "severity": self.severity.value,
            "source": self.source.value,
            "auto_correctable": self.auto_correctable,
            "netbox_id": self.netbox_id,
            "netbox_endpoint": self.netbox_endpoint,
            "identifier": self.identifier,
            "additional_context": self.additional_context,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DiffResult":
        """Create from dictionary."""
        return cls(
            entity_type=EntityType(data["entity_type"]),
            device=data["device"],
            field=data["field"],
            network_value=data["network_value"],
            netbox_value=data["netbox_value"],
            severity=DiffSeverity(data["severity"]),
            source=DiffSource(data["source"]),
            auto_correctable=data.get("auto_correctable", False),
            netbox_id=data.get("netbox_id"),
            netbox_endpoint=data.get("netbox_endpoint"),
            identifier=data.get("identifier"),
            additional_context=data.get("additional_context", {}),
        )


@dataclass
class ReconciliationReport:
    """
    Complete reconciliation report for a set of devices.
    
    Attributes:
        timestamp: When the comparison was performed
        device_scope: List of devices that were compared
        total_entities: Total entities examined
        matched: Number of entities that match
        mismatched: Number of entities with differences
        missing_in_netbox: Entities in network but not NetBox
        missing_in_network: Entities in NetBox but not network
        diffs: List of individual differences
        summary_by_type: Count of diffs by entity type
        summary_by_severity: Count of diffs by severity
    """
    timestamp: datetime = field(default_factory=datetime.now)
    device_scope: list[str] = field(default_factory=list)
    total_entities: int = 0
    matched: int = 0
    mismatched: int = 0
    missing_in_netbox: int = 0
    missing_in_network: int = 0
    diffs: list[DiffResult] = field(default_factory=list)
    summary_by_type: dict[str, int] = field(default_factory=dict)
    summary_by_severity: dict[str, int] = field(default_factory=dict)
    
    def add_diff(self, diff: DiffResult) -> None:
        """Add a diff result and update summaries."""
        self.diffs.append(diff)
        self.mismatched += 1
        
        # Update type summary
        type_key = diff.entity_type.value
        self.summary_by_type[type_key] = self.summary_by_type.get(type_key, 0) + 1
        
        # Update severity summary
        sev_key = diff.severity.value
        self.summary_by_severity[sev_key] = self.summary_by_severity.get(sev_key, 0) + 1
    
    def add_match(self) -> None:
        """Record a matching entity."""
        self.matched += 1
        self.total_entities += 1
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "device_scope": self.device_scope,
            "total_entities": self.total_entities,
            "matched": self.matched,
            "mismatched": self.mismatched,
            "missing_in_netbox": self.missing_in_netbox,
            "missing_in_network": self.missing_in_network,
            "diffs": [d.to_dict() for d in self.diffs],
            "summary_by_type": self.summary_by_type,
            "summary_by_severity": self.summary_by_severity,
        }
    
    def to_markdown(self) -> str:
        """Generate markdown report."""
        lines = [
            f"# NetBox Sync Report - {self.timestamp.strftime('%Y-%m-%d %H:%M')}",
            "",
            "## Summary",
            f"- **Devices**: {', '.join(self.device_scope)}",
            f"- **Total Entities**: {self.total_entities}",
            f"- **Matched**: {self.matched}",
            f"- **Mismatched**: {self.mismatched}",
            f"- **Missing in NetBox**: {self.missing_in_netbox}",
            f"- **Missing in Network**: {self.missing_in_network}",
            "",
            "## By Entity Type",
        ]
        
        for entity_type, count in self.summary_by_type.items():
            lines.append(f"- {entity_type}: {count}")
        
        lines.extend(["", "## By Severity"])
        for severity, count in self.summary_by_severity.items():
            emoji = {"info": "ℹ️", "warning": "⚠️", "critical": "🔴"}.get(severity, "")
            lines.append(f"- {emoji} {severity}: {count}")
        
        if self.diffs:
            lines.extend(["", "## Differences", ""])
            lines.append("| Device | Type | Field | Network | NetBox | Severity | Auto-Fix |")
            lines.append("|--------|------|-------|---------|--------|----------|----------|")
            for diff in self.diffs[:50]:  # Limit to 50 rows
                auto = "✅" if diff.auto_correctable else "❌"
                # For existence diffs, show identifier instead of present/missing
                if diff.field == "existence":
                    network_val = diff.identifier if diff.network_value == "present" else "missing"
                    netbox_val = diff.netbox_value if diff.netbox_value != "missing" else "missing"
                else:
                    network_val = diff.network_value
                    netbox_val = diff.netbox_value
                lines.append(
                    f"| {diff.device} | {diff.entity_type.value} | {diff.field} | "
                    f"{network_val} | {netbox_val} | {diff.severity.value} | {auto} |"
                )
            
            if len(self.diffs) > 50:
                lines.append(f"\n*... and {len(self.diffs) - 50} more differences*")
        
        return "\n".join(lines)


@dataclass
class ReconcileResult:
    """
    Result of a reconciliation operation.
    
    Attributes:
        diff: The original difference
        action: Action that was taken
        success: Whether the action succeeded
        message: Human-readable result message
        netbox_response: Raw NetBox API response (if applicable)
    """
    diff: DiffResult
    action: ReconcileAction
    success: bool
    message: str
    netbox_response: dict[str, Any] | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "diff": self.diff.to_dict(),
            "action": self.action.value,
            "success": self.success,
            "message": self.message,
            "netbox_response": self.netbox_response,
        }
