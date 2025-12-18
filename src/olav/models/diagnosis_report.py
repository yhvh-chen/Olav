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
from pathlib import Path
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

    # Investigation Process (for detailed report)
    investigation_process: list[str] = Field(
        default_factory=list,
        description="Step-by-step investigation process with timestamps"
    )
    duration_seconds: float = Field(
        default=0.0,
        description="Total investigation duration in seconds"
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
        """Render full Markdown report with device details.

        Returns:
            Formatted Markdown string
        """
        evidence = "\n".join(f"- {e}" for e in self.evidence_chain) if self.evidence_chain else "- No evidence collected."

        # Device summaries with detailed findings
        device_sections = []
        for name, summary in self.device_summaries.items():
            status_icon = {"faulty": "❌", "degraded": "⚠️", "healthy": "✅"}.get(summary.status, "❓")
            findings_lines = []
            for layer, findings in summary.layer_findings.items():
                if findings:
                    for f in findings[:3]:
                        findings_lines.append(f"  - {layer}: {f}")
            findings_text = "\n".join(findings_lines) if findings_lines else "  - No issues detected"
            device_sections.append(f"### {status_icon} {name} ({summary.status})\n{findings_text}")
        devices_text = "\n\n".join(device_sections) if device_sections else "_No devices analyzed._"

        return f"""# 🔍 Network Diagnosis Report

**Report ID**: `{self.report_id}`  
**Timestamp**: {self.timestamp}

---

## 📋 Query

> {self.fault_description}

## 🎯 Root Cause

| Field | Value |
|-------|-------|
| **Cause** | {self.root_cause} |
| **Device** | `{self.root_cause_device or 'Unknown'}` |
| **Layer** | {self.root_cause_layer or 'Unknown'} |
| **Confidence** | **{self.confidence*100:.0f}%** |

## 📊 Evidence

{evidence}

## 🖥️ Device Analysis

{devices_text}

## 💡 Recommended Action

{self.recommended_action or '_No specific action recommended._'}

---

*Tags*: {', '.join(self.tags) if self.tags else 'None'} | *Protocols*: {', '.join(self.affected_protocols) if self.affected_protocols else 'None'} | *Layers*: {', '.join(self.affected_layers) if self.affected_layers else 'N/A'} | *Path*: {' → '.join(self.fault_path) if self.fault_path else 'N/A'}
"""

    def render_detailed_markdown(self) -> str:
        """Render detailed Markdown report with investigation process.

        Similar to Inspection report style, includes:
        - Investigation process steps
        - Detailed findings by layer
        - Root cause analysis
        - Recommended actions

        Returns:
            Formatted Markdown string
        """
        # Determine overall status
        if self.confidence >= 0.8:
            status_icon = "🟢"
            status_text = "HIGH CONFIDENCE"
        elif self.confidence >= 0.5:
            status_icon = "🟡"
            status_text = "MEDIUM CONFIDENCE"
        else:
            status_icon = "🔴"
            status_text = "LOW CONFIDENCE"

        # Format duration
        duration = self.duration_seconds
        if duration >= 3600:
            duration_str = f"{duration / 3600:.1f}h"
        elif duration >= 60:
            duration_str = f"{duration / 60:.1f}m"
        else:
            duration_str = f"{duration:.1f}s"

        # Format timestamp
        try:
            ts = datetime.fromisoformat(self.timestamp)
            time_str = ts.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            time_str = self.timestamp[:19]

        # Header
        lines = [
            f"# {status_icon} Network Diagnosis Report — {status_text}",
            "",
            f"> **ID**: `{self.report_id}`  ",
            f"> **Time**: {time_str} · **Duration**: {duration_str}  ",
            f"> **Confidence**: {self.confidence*100:.0f}%",
            "",
        ]

        # Original Query
        lines.extend([
            "## 📋 Original Query",
            "",
            f"> {self.fault_description}",
            "",
        ])

        # Investigation Process
        if self.investigation_process:
            lines.extend([
                "## 🔍 Investigation Process",
                "",
            ])
            for i, step in enumerate(self.investigation_process, 1):
                lines.append(f"{i}. {step}")
            lines.append("")

        # Root Cause Analysis
        lines.extend([
            "## 🎯 Root Cause",
            "",
            "| Field | Value |",
            "|-------|-------|",
            f"| **Cause** | {self.root_cause} |",
            f"| **Device** | `{self.root_cause_device or 'Unknown'}` |",
            f"| **Layer** | {self.root_cause_layer or 'Unknown'} |",
            f"| **Confidence** | **{self.confidence*100:.0f}%** |",
            "",
        ])

        # Evidence Chain
        if self.evidence_chain:
            lines.extend([
                "## 📊 Evidence",
                "",
            ])
            for e in self.evidence_chain:
                lines.append(f"- {e}")
            lines.append("")

        # Device Analysis (detailed)
        if self.device_summaries:
            lines.extend([
                "## 🖥️ Device Analysis",
                "",
            ])

            # Group by status
            faulty = [(n, s) for n, s in self.device_summaries.items() if s.status == "faulty"]
            degraded = [(n, s) for n, s in self.device_summaries.items() if s.status == "degraded"]
            healthy = [(n, s) for n, s in self.device_summaries.items() if s.status == "healthy"]

            # Faulty devices first
            if faulty:
                lines.append("### ❌ Faulty Devices\n")
                for name, summary in faulty:
                    self._append_device_details(lines, name, summary)

            # Degraded devices
            if degraded:
                lines.append("### ⚠️ Degraded Devices\n")
                for name, summary in degraded:
                    self._append_device_details(lines, name, summary)

            # Healthy devices (collapsed)
            if healthy:
                lines.append(f"### ✅ Healthy Devices ({len(healthy)})\n")
                lines.append(", ".join(f"`{n}`" for n, _ in healthy))
                lines.append("")

        # Recommended Action
        if self.recommended_action:
            lines.extend([
                "## 💡 Recommended Action",
                "",
                self.recommended_action,
                "",
            ])

        # Metadata footer
        lines.extend([
            "---",
            "",
            f"*Tags*: {', '.join(self.tags) if self.tags else 'None'} | "
            f"*Protocols*: {', '.join(self.affected_protocols) if self.affected_protocols else 'None'} | "
            f"*Layers*: {', '.join(self.affected_layers) if self.affected_layers else 'N/A'}",
            "",
            f"*Fault Path*: {' → '.join(self.fault_path) if self.fault_path else 'N/A'}",
        ])

        return "\n".join(lines)

    def _append_device_details(self, lines: list[str], name: str, summary: "DeviceSummary") -> None:
        """Append device details to lines."""
        lines.append(f"**{name}** (confidence: {summary.confidence*100:.0f}%)")
        lines.append("")

        # Layer findings table
        has_findings = any(summary.layer_findings.get(layer) for layer in ["L1", "L2", "L3", "L4"])
        if has_findings:
            lines.append("| Layer | Findings |")
            lines.append("|-------|----------|")
            for layer in ["L1", "L2", "L3", "L4"]:
                findings = summary.layer_findings.get(layer, [])
                if findings:
                    # Join multiple findings
                    findings_text = "; ".join(findings[:3])
                    if len(findings) > 3:
                        findings_text += f" (+{len(findings)-3} more)"
                    lines.append(f"| {layer} | {findings_text} |")
            lines.append("")
        else:
            lines.append("_No specific findings._\n")

    def save(self, output_dir: Path | str | None = None) -> Path:
        """Save report to local file.

        Args:
            output_dir: Optional output directory. Defaults to data/reports.

        Returns:
            Path to saved report file.
        """
        from config.settings import get_path

        # Use provided dir or default
        if output_dir:
            reports_dir = Path(output_dir)
            reports_dir.mkdir(parents=True, exist_ok=True)
        else:
            reports_dir = get_path("reports")

        # Generate filename: diagnosis_{report_id}_{timestamp}.md
        # Parse timestamp for filename
        try:
            ts = datetime.fromisoformat(self.timestamp)
            ts_str = ts.strftime("%Y%m%d_%H%M%S")
        except Exception:
            ts_str = self.timestamp[:19].replace(":", "").replace("-", "")

        # Use short report ID
        short_id = self.report_id.split("-")[-1] if "-" in self.report_id else self.report_id[:8]
        filename = f"diagnosis_{short_id}_{ts_str}.md"
        report_path = reports_dir / filename

        # Generate detailed markdown content
        content = self.render_detailed_markdown()

        # Write report
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(content)

        return report_path


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
    tag_keywords = {
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

    for tag, keywords in tag_keywords.items():
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
    protocols = [
        "bgp", "ospf", "isis", "eigrp", "rip",
        "stp", "rstp", "mstp", "pvst",
        "lacp", "lldp", "cdp",
        "vxlan", "mpls", "gre",
        "dhcp", "dns", "ntp",
        "snmp", "netconf", "ssh",
    ]

    text_lower = text.lower()
    return [p for p in protocols if p in text_lower]


def extract_layers(findings: dict[str, list[str]]) -> list[str]:
    """Extract affected layers from findings dict.

    Args:
        findings: Layer -> findings mapping

    Returns:
        List of layers with non-empty findings
    """
    return [layer for layer, items in findings.items() if items]


__all__ = [
    "DeviceSummary",
    "DiagnosisReport",
    "SimilarCase",
    "extract_layers",
    "extract_protocols",
    "extract_tags_from_text",
]
