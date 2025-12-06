# OLAV - Diagnosis Report Data Model
"""
DiagnosisReport model for structured diagnosis results.

This model is used for:
1. Generating structured reports from workflow outputs
2. Indexing to OpenSearch for Agentic RAG
3. Rendering Markdown reports for users
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DeviceSummary(BaseModel):
    """Summary of findings for a single device."""

    device: str = Field(description="Device hostname")
    status: str = Field(description="Overall status: healthy, degraded, faulty")
    layer_findings: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Findings by layer: {L1: [...], L2: [...], ...}"
    )
    confidence: float = Field(default=0.0, description="Confidence 0-1")


class DiagnosisReport(BaseModel):
    """Structured diagnosis report for indexing and display.

    This is the core data structure for Agentic RAG knowledge base.
    Reports are indexed to OpenSearch with embeddings for semantic search.
    """

    # Identification
    report_id: str = Field(
        default_factory=lambda: f"diag-{uuid.uuid4().hex[:12]}",
        description="Unique report ID"
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="Report generation timestamp"
    )

    # Query/Alert Information
    fault_description: str = Field(description="Original fault description or user query")
    source: str | None = Field(default=None, description="Source device/host")
    destination: str | None = Field(default=None, description="Destination device/host")
    fault_path: list[str] = Field(default_factory=list, description="Devices on fault path")

    # Diagnosis Results
    root_cause: str = Field(description="Identified root cause")
    root_cause_device: str | None = Field(default=None, description="Device where root cause is located")
    root_cause_layer: str | None = Field(default=None, description="Network layer: L1, L2, L3, L4")
    confidence: float = Field(description="Confidence in root cause 0-1")

    # Evidence
    evidence_chain: list[str] = Field(
        default_factory=list,
        description="Chain of evidence leading to conclusion"
    )
    device_summaries: dict[str, DeviceSummary] = Field(
        default_factory=dict,
        description="Per-device summaries"
    )

    # Resolution
    recommended_action: str = Field(default="", description="Suggested fix")
    resolution_applied: bool = Field(default=False, description="Whether fix was applied")
    resolution_result: str | None = Field(default=None, description="Result of fix if applied")

    # Metadata for RAG
    tags: list[str] = Field(
        default_factory=list,
        description="Tags: bgp, interface, acl, ..."
    )
    affected_protocols: list[str] = Field(
        default_factory=list,
        description="Protocols involved: ospf, bgp, stp, ..."
    )
    affected_layers: list[str] = Field(
        default_factory=list,
        description="Layers with issues: L1, L2, ..."
    )

    # Report Content
    markdown_content: str = Field(default="", description="Full Markdown report")

    def to_opensearch_doc(self) -> dict[str, Any]:
        """Convert to OpenSearch document format.

        Does not include embeddings - those are added separately.
        """
        doc = self.model_dump()
        # Flatten device_summaries for OpenSearch
        doc["device_summaries_text"] = "\n".join(
            f"{name}: {summary.status}"
            for name, summary in self.device_summaries.items()
        )
        return doc

    def render_markdown(self) -> str:
        """Render full Markdown report.

        Returns:
            Formatted Markdown string
        """
        evidence = "\n".join(f"- {e}" for e in self.evidence_chain) if self.evidence_chain else "No evidence collected."

        device_sections = []
        for name, summary in self.device_summaries.items():
            findings_text = ""
            for layer, findings in summary.layer_findings.items():
                if findings:
                    findings_text += f"\n  - **{layer}**: {', '.join(findings[:3])}"
            device_sections.append(f"- **{name}** ({summary.status}){findings_text}")
        devices_text = "\n".join(device_sections) if device_sections else "No device summaries."

        md = f"""# 🔍 Network Diagnosis Report

**Report ID**: `{self.report_id}`
**Timestamp**: {self.timestamp}

---

## 📋 Fault Description

{self.fault_description}

## 🎯 Root Cause Analysis

| Field | Value |
|-------|-------|
| **Root Cause** | {self.root_cause} |
| **Device** | {self.root_cause_device or 'Unknown'} |
| **Layer** | {self.root_cause_layer or 'Unknown'} |
| **Confidence** | {self.confidence*100:.0f}% |

## 📊 Evidence Chain

{evidence}

## 🖥️ Device Summaries

{devices_text}

## 💡 Recommended Action

{self.recommended_action or 'No specific action recommended.'}

---

## 🏷️ Metadata

- **Tags**: {', '.join(self.tags) if self.tags else 'None'}
- **Protocols**: {', '.join(self.affected_protocols) if self.affected_protocols else 'None'}
- **Layers**: {', '.join(self.affected_layers) if self.affected_layers else 'None'}
- **Fault Path**: {' → '.join(self.fault_path) if self.fault_path else 'Not determined'}
"""
        return md


class SimilarCase(BaseModel):
    """A similar case from knowledge base (Agentic RAG result)."""

    case_id: str = Field(description="Report ID of similar case")
    fault_description: str = Field(description="Original fault description")
    root_cause: str = Field(description="Root cause that was identified")
    resolution: str = Field(description="How it was resolved")
    similarity_score: float = Field(description="Similarity score 0-1")
    timestamp: str | None = Field(default=None, description="When the case occurred")
    tags: list[str] = Field(default_factory=list, description="Case tags")


# =============================================================================
# Helper Functions
# =============================================================================


def extract_tags_from_text(text: str) -> list[str]:
    """Extract relevant network tags from text.

    Args:
        text: Text to analyze (root cause, findings, etc.)

    Returns:
        List of relevant tags
    """
    TAG_KEYWORDS = {
        "bgp": ["bgp", "peer", "neighbor", "as ", "asn"],
        "ospf": ["ospf", "area", "lsa", "spf"],
        "interface": ["interface", "port", "link", "down", "up"],
        "vlan": ["vlan", "trunk", "access"],
        "routing": ["route", "routing", "next-hop", "rib"],
        "acl": ["acl", "access-list", "filter", "deny", "permit"],
        "stp": ["stp", "spanning", "blocked", "root"],
        "mtu": ["mtu", "fragmentation", "jumbo"],
        "arp": ["arp", "mac", "neighbor"],
        "connectivity": ["ping", "reach", "unreachable", "timeout"],
    }

    text_lower = text.lower()
    tags = []

    for tag, keywords in TAG_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            tags.append(tag)

    return tags


def extract_protocols(text: str) -> list[str]:
    """Extract protocol names from text.

    Args:
        text: Text to analyze

    Returns:
        List of protocol names
    """
    PROTOCOLS = [
        "bgp", "ospf", "isis", "eigrp", "rip",
        "stp", "rstp", "mstp", "pvst",
        "lacp", "lldp", "cdp",
        "vxlan", "mpls", "gre",
        "dhcp", "dns", "ntp",
        "snmp", "netconf", "ssh",
    ]

    text_lower = text.lower()
    return [p for p in PROTOCOLS if p in text_lower]


def extract_layers(findings: dict[str, list[str]]) -> list[str]:
    """Extract affected layers from findings dict.

    Args:
        findings: Layer -> findings mapping

    Returns:
        List of layers with non-empty findings
    """
    return [layer for layer, items in findings.items() if items]


__all__ = [
    "DiagnosisReport",
    "DeviceSummary",
    "SimilarCase",
    "extract_tags_from_text",
    "extract_protocols",
    "extract_layers",
]
