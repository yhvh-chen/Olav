"""Expert Mode Report Generator - Diagnosis report + Agentic indexing.

The Report Generator:
1. Generates structured diagnosis reports from investigation results
2. Indexes successful diagnoses to Episodic Memory (Agentic closed-loop)
3. Formats reports for user presentation

Agentic Learning Loop:
    Diagnosis Complete → ReportGenerator.generate_and_index()
    → MemoryStoreTool → olav-episodic-memory index
    → Future kb_search can retrieve this case
"""

import logging
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from olav.tools.opensearch_tool import MemoryStoreTool

logger = logging.getLogger(__name__)


# =============================================================================
# Data Models
# =============================================================================


class EvidenceItem(BaseModel):
    """A single piece of evidence in the diagnosis chain."""

    phase: Literal["phase1", "phase2"]
    source: str  # "suzieq", "cli", "netconf"
    finding: str
    confidence: float
    device: str | None = None
    raw_data: str | None = None


class DiagnosisReport(BaseModel):
    """Structured diagnosis report."""

    # Original query
    original_query: str

    # Root cause
    root_cause_found: bool
    root_cause: str | None = None
    root_cause_type: Literal["config_policy", "hardware", "protocol", "unknown"] | None = None

    # Classification
    layer: Literal["L1", "L2", "L3", "L4"] | None = None

    # Affected resources
    affected_devices: list[str] = Field(default_factory=list)
    relevant_configs: list[str] = Field(default_factory=list)  # ["route-map bgp_out", ...]

    # Evidence chain
    evidence_chain: list[EvidenceItem] = Field(default_factory=list)

    # Recommendations (read-only mode - no execution)
    recommended_resolution: str | None = None

    # Metadata
    duration_seconds: float = 0.0
    rounds_executed: int = 0
    phase2_executed: bool = False
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Human-readable summary
    summary: str | None = None


# =============================================================================
# Report Generator
# =============================================================================


class ReportGenerator:
    """Generate diagnosis reports and index to Episodic Memory.

    Implements Agentic closed-loop:
    1. Generate structured report from diagnosis state
    2. Index to olav-episodic-memory for future reference
    3. Format for user presentation

    Usage:
        generator = ReportGenerator()
        report = await generator.generate_and_index(
            diagnosis_state=state,
            index_to_memory=True
        )

        # Alternative: simple generate() for workflow integration
        text_report = generator.generate(
            query="R1 无法 ping 通 R2",
            state=supervisor_state,
            phase2_executed=True,
            phase2_findings=["R1 route-map blocks prefix"],
        )
    """

    def __init__(self) -> None:
        """Initialize report generator."""
        self.memory_store = MemoryStoreTool()

    def generate(
        self,
        query: str,
        state: Any,  # SupervisorState
        phase2_executed: bool = False,
        phase2_findings: list[str] | None = None,
    ) -> str:
        """Generate a text report for workflow integration.

        Simpler interface for ExpertModeWorkflow.

        Args:
            query: Original user query.
            state: SupervisorState with diagnosis results.
            phase2_executed: Whether Phase 2 was executed.
            phase2_findings: Findings from Phase 2.

        Returns:
            Formatted text report.
        """
        phase2_findings = phase2_findings or []

        lines = [
            "=" * 60,
            "OLAV Expert Mode 诊断报告",
            "=" * 60,
            "",
            f"查询: {query}",
            f"时间: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')} UTC",
            f"执行轮次: {state.current_round}",
            f"Phase 2 执行: {'是' if phase2_executed else '否'}",
            "",
        ]

        # Root cause
        lines.append("-" * 40)
        if state.root_cause_found:
            lines.append("✅ 根因已定位:")
            lines.append(f"   {state.root_cause}")
        else:
            lines.append("⚠️ 根因未确定")
            lines.append("   建议: 需要进一步调查或收集更多数据")
        lines.append("")

        # Phase 1 Layer findings
        lines.append("-" * 40)
        lines.append("Phase 1 分析结果 (SuzieQ 历史数据):")
        lines.append("")

        for layer, status in state.layer_coverage.items():
            if status.checked:
                bar = self._confidence_bar(status.confidence)
                lines.append(f"  [{layer}] {bar} ({status.confidence:.0%})")
                for finding in status.findings:
                    lines.append(f"    • {finding}")
                if not status.findings:
                    lines.append("    • (无异常发现)")
                lines.append("")

        # Phase 2 findings
        if phase2_executed and phase2_findings:
            lines.append("-" * 40)
            lines.append("Phase 2 验证结果 (CLI/NETCONF 实时数据):")
            lines.append("")
            for finding in phase2_findings:
                lines.append(f"  • {finding}")
            lines.append("")

        # Summary
        max_conf = max(
            (s.confidence for s in state.layer_coverage.values()),
            default=0.0
        )
        lines.append("=" * 60)
        lines.append(f"最终置信度: {max_conf:.0%}")
        lines.append("=" * 60)

        return "\n".join(lines)

    def _confidence_bar(self, confidence: float, width: int = 10) -> str:
        """Generate visual confidence bar."""
        filled = int(confidence * width)
        empty = width - filled
        return f"[{'█' * filled}{'░' * empty}]"

    async def index_to_episodic_memory(
        self,
        query: str,
        root_cause: str,
        findings: list[str],
        phase2_executed: bool = False,
    ) -> bool:
        """Index diagnosis to Episodic Memory for workflow integration.

        Simpler interface for ExpertModeWorkflow.

        Args:
            query: Original user query.
            root_cause: Identified root cause.
            findings: All findings from Phase 1 + Phase 2.
            phase2_executed: Whether Phase 2 was executed.

        Returns:
            True if indexing succeeded, False otherwise.
        """
        document = {
            "query": query,
            "root_cause": root_cause,
            "findings": findings,
            "phase2_executed": phase2_executed,
            "timestamp": datetime.now(UTC).isoformat(),
            "content": f"问题: {query}\n根因: {root_cause}\n发现: {'; '.join(findings)}",
        }

        doc_id = f"diag-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{hash(query) % 10000:04d}"

        try:
            result = await self.memory_store.execute(
                index="olav-episodic-memory",
                document=document,
                doc_id=doc_id,
            )

            if result.error:
                logger.warning(f"Failed to index diagnosis: {result.error}")
                return False

            logger.info(f"Indexed diagnosis to episodic memory: {doc_id}")
            return True

        except Exception as e:
            logger.exception(f"Error indexing to episodic memory: {e}")
            return False

    async def generate_and_index(
        self,
        diagnosis_state: Any,  # SupervisorState
        index_to_memory: bool = True,
    ) -> DiagnosisReport:
        """Generate report and index to Episodic Memory.

        Args:
            diagnosis_state: SupervisorState with diagnosis results.
            index_to_memory: Whether to index successful diagnoses.

        Returns:
            DiagnosisReport with structured findings.
        """
        # Generate report from state
        report = self._generate_report(diagnosis_state)

        # Index to memory if successful diagnosis
        if index_to_memory and report.root_cause_found:
            await self._index_to_episodic_memory(report)
            logger.info(f"Indexed diagnosis to episodic memory: {report.root_cause}")

        return report

    def _generate_report(self, state: Any) -> DiagnosisReport:
        """Generate DiagnosisReport from SupervisorState.

        Args:
            state: SupervisorState with layer coverage, findings, etc.

        Returns:
            Structured DiagnosisReport.
        """
        # Extract evidence from layer coverage
        evidence_chain = []
        affected_devices = set()
        relevant_configs = []

        for _layer_name, layer_status in state.layer_coverage.items():
            if layer_status.findings:
                for finding in layer_status.findings:
                    evidence_chain.append(EvidenceItem(
                        phase="phase1",  # TODO: track phase in findings
                        source="suzieq",
                        finding=finding,
                        confidence=layer_status.confidence,
                        device=None,
                    ))

                    # Extract device names from findings
                    import re
                    device_matches = re.findall(r"\b(R\d+|SW\d+|S\d+)\b", finding)
                    affected_devices.update(device_matches)

                    # Extract config references
                    config_matches = re.findall(
                        r"(route-map \S+|prefix-list \S+|access-list \S+)",
                        finding,
                        re.IGNORECASE
                    )
                    relevant_configs.extend(config_matches)

        # Determine root cause type
        root_cause_type = None
        if state.root_cause:
            root_cause_lower = state.root_cause.lower()
            if any(kw in root_cause_lower for kw in ["route-map", "prefix-list", "acl", "policy"]):
                root_cause_type = "config_policy"
            elif any(kw in root_cause_lower for kw in ["down", "error", "crc", "cable"]):
                root_cause_type = "hardware"
            elif any(kw in root_cause_lower for kw in ["bgp", "ospf", "protocol", "neighbor"]):
                root_cause_type = "protocol"
            else:
                root_cause_type = "unknown"

        # Determine primary layer
        primary_layer = None
        max_confidence = 0.0
        for layer_name, layer_status in state.layer_coverage.items():
            if layer_status.confidence > max_confidence and layer_status.findings:
                max_confidence = layer_status.confidence
                primary_layer = layer_name

        # Generate summary
        summary = self._generate_summary(state, evidence_chain)

        return DiagnosisReport(
            original_query=state.query,
            root_cause_found=state.root_cause_found,
            root_cause=state.root_cause,
            root_cause_type=root_cause_type,
            layer=primary_layer,
            affected_devices=list(affected_devices),
            relevant_configs=list(set(relevant_configs)),
            evidence_chain=evidence_chain,
            recommended_resolution=self._generate_resolution(state),
            duration_seconds=0.0,  # TODO: track duration
            rounds_executed=state.current_round,
            phase2_executed=False,  # TODO: track phase2
            summary=summary,
        )

    def _generate_summary(self, state: Any, evidence: list[EvidenceItem]) -> str:
        """Generate human-readable summary.

        Args:
            state: SupervisorState
            evidence: Evidence chain

        Returns:
            Markdown-formatted summary.
        """
        lines = ["## 诊断报告\n"]

        lines.append(f"**查询**: {state.query}\n")

        if state.root_cause_found:
            lines.append("### ✅ 根因已确认\n")
            lines.append(f"**根因**: {state.root_cause}\n")
        else:
            lines.append("### ⚠️ 根因未完全确认\n")
            lines.append("需要进一步调查或 Phase 2 实时验证。\n")

        lines.append("\n### 证据链\n")
        for i, e in enumerate(evidence[:10], 1):
            lines.append(f"{i}. [{e.phase.upper()}] {e.finding} (置信度: {e.confidence*100:.0f}%)")

        lines.append("\n### 层级覆盖\n")
        lines.append(state.get_coverage_summary())

        return "\n".join(lines)

    def _generate_resolution(self, state: Any) -> str | None:
        """Generate recommended resolution.

        Args:
            state: SupervisorState

        Returns:
            Resolution recommendation or None.
        """
        if not state.root_cause:
            return None

        root_cause_lower = state.root_cause.lower()

        # Route-map / prefix-list issues
        if "route-map" in root_cause_lower or "prefix-list" in root_cause_lower:
            return (
                "建议检查并修改相关的 route-map 或 prefix-list 配置，"
                "确保目标前缀被正确匹配和放行。"
                "\n\n**注意**: Expert Mode 为只读模式，请手动执行配置变更。"
            )

        # Interface down
        if "down" in root_cause_lower and "interface" in root_cause_lower:
            return (
                "建议检查接口物理状态和配置，"
                "确认线缆连接和 no shutdown 配置。"
            )

        # BGP neighbor issues
        if "bgp" in root_cause_lower and "neighbor" in root_cause_lower:
            return (
                "建议检查 BGP 邻居配置，确认 AS 号、IP 地址和认证配置正确。"
            )

        return "建议进一步分析相关配置和状态。"

    async def _index_to_episodic_memory(self, report: DiagnosisReport) -> None:
        """Index successful diagnosis to Episodic Memory.

        Enables Agentic learning loop - future similar queries
        can retrieve this diagnosis via kb_search.

        Args:
            report: Completed DiagnosisReport
        """
        document = {
            # Searchable fields
            "query": report.original_query,
            "root_cause": report.root_cause,
            "root_cause_type": report.root_cause_type,
            "layer": report.layer,

            # Context for retrieval
            "devices": report.affected_devices,
            "config_sections": report.relevant_configs,

            # Evidence chain (nested)
            "evidence_chain": [
                {
                    "phase": e.phase,
                    "source": e.source,
                    "finding": e.finding,
                    "confidence": e.confidence,
                }
                for e in report.evidence_chain[:10]
            ],

            # Resolution
            "resolution": report.recommended_resolution,

            # Metadata
            "diagnosis_duration_seconds": report.duration_seconds,
            "rounds_executed": report.rounds_executed,
            "phase2_executed": report.phase2_executed,
            "timestamp": report.timestamp.isoformat(),

            # Summary for display
            "summary": report.summary,
        }

        # Generate unique doc ID
        doc_id = f"diag-{report.timestamp.strftime('%Y%m%d%H%M%S')}-{hash(report.original_query) % 10000:04d}"

        try:
            result = await self.memory_store.execute(
                index="olav-episodic-memory",
                document=document,
                doc_id=doc_id,
            )

            if result.error:
                logger.warning(f"Failed to index diagnosis: {result.error}")
            else:
                logger.info(f"Indexed diagnosis to episodic memory: {doc_id}")

        except Exception as e:
            logger.exception(f"Error indexing to episodic memory: {e}")

    def format_for_display(self, report: DiagnosisReport) -> str:
        """Format report for CLI/UI display.

        Args:
            report: DiagnosisReport

        Returns:
            Formatted string for display.
        """
        if report.summary:
            return report.summary

        return self._generate_summary_from_report(report)

    def _generate_summary_from_report(self, report: DiagnosisReport) -> str:
        """Generate summary from DiagnosisReport (fallback).

        Args:
            report: DiagnosisReport

        Returns:
            Markdown summary.
        """
        lines = ["## 诊断报告\n"]
        lines.append(f"**查询**: {report.original_query}\n")

        if report.root_cause_found:
            lines.append(f"### ✅ 根因: {report.root_cause}\n")
            lines.append(f"- **层级**: {report.layer}")
            lines.append(f"- **类型**: {report.root_cause_type}")
            lines.append(f"- **设备**: {', '.join(report.affected_devices)}")
            if report.relevant_configs:
                lines.append(f"- **配置**: {', '.join(report.relevant_configs)}")
        else:
            lines.append("### ⚠️ 需要进一步调查\n")

        if report.recommended_resolution:
            lines.append(f"\n### 建议\n{report.recommended_resolution}")

        return "\n".join(lines)
