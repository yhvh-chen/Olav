"""Expert Mode Supervisor - Orchestrates multi-step fault diagnosis.

The Supervisor:
1. Analyzes KB + Syslog for fault scope narrowing (Round 0)
2. Tracks L1-L4 layer confidence
3. Assigns tasks to QuickAnalyzer
4. Determines when root cause is found
5. Generates final diagnosis report

Architecture:
    Query → Supervisor (Track L1-L4 Confidence) ↔ QuickAnalyzer (ReAct)
"""

import logging
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

NETWORK_LAYERS = ("L1", "L2", "L3", "L4")

LAYER_INFO = {
    "L1": {
        "name": "Physical Layer",
        "description": "接口状态、错误计数、链路状态、线缆",
        "suzieq_tables": ["interfaces", "device"],
        "keywords": ["接口", "interface", "link", "down", "up", "cable", "物理"],
    },
    "L2": {
        "name": "Data Link Layer",
        "description": "VLAN、MAC 表、STP、LLDP 邻居",
        "suzieq_tables": ["vlan", "macs", "lldp", "stp"],
        "keywords": ["vlan", "mac", "stp", "lldp", "二层", "交换"],
    },
    "L3": {
        "name": "Network Layer",
        "description": "IP 地址、路由表、BGP/OSPF、ARP",
        "suzieq_tables": ["routes", "bgp", "ospf", "arpnd", "address"],
        "keywords": ["route", "路由", "bgp", "ospf", "arp", "ip", "三层", "网络层"],
    },
    "L4": {
        "name": "Transport Layer",
        "description": "TCP/UDP 连接、会话状态、NAT",
        "suzieq_tables": [],  # Limited SuzieQ coverage
        "keywords": ["tcp", "udp", "session", "nat", "四层", "传输层"],
    },
}

# Confidence thresholds
MIN_ACCEPTABLE_CONFIDENCE = 0.5  # 50% minimum per layer
SUZIEQ_MAX_CONFIDENCE = 0.60  # Historical data cap
REALTIME_CONFIDENCE = 0.95  # CLI/NETCONF verification


# =============================================================================
# Data Models
# =============================================================================


class LayerStatus(BaseModel):
    """Status tracking for a single network layer."""

    layer: str
    checked: bool = False
    confidence: float = 0.0
    findings: list[str] = Field(default_factory=list)
    last_checked: str | None = None

    def update(self, new_confidence: float, new_findings: list[str]) -> None:
        """Update layer with new check results."""
        self.checked = True
        self.confidence = max(self.confidence, new_confidence)
        self.findings.extend(new_findings)
        self.last_checked = datetime.now().isoformat()

    @property
    def needs_investigation(self) -> bool:
        """Check if layer needs more investigation."""
        return self.confidence < MIN_ACCEPTABLE_CONFIDENCE


class DiagnosisTask(BaseModel):
    """Task assigned by Supervisor to QuickAnalyzer."""

    task_id: int
    layer: str
    description: str
    suggested_tables: list[str] = Field(default_factory=list)
    suggested_filters: dict[str, Any] = Field(default_factory=dict)
    priority: Literal["high", "medium", "low"] = "medium"


class DiagnosisResult(BaseModel):
    """Result from QuickAnalyzer."""

    task_id: int
    layer: str
    success: bool
    confidence: float = 0.0
    findings: list[str] = Field(default_factory=list)
    tool_outputs: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None


class SupervisorState(BaseModel):
    """Supervisor's internal state."""

    query: str
    path_devices: list[str] = Field(default_factory=list)

    # L1-L4 tracking
    layer_coverage: dict[str, LayerStatus] = Field(default_factory=dict)

    # Round tracking
    current_round: int = 0
    max_rounds: int = 5

    # Current task
    current_task: DiagnosisTask | None = None

    # KB + Syslog context (Round 0)
    similar_cases: list[dict[str, Any]] = Field(default_factory=list)
    syslog_events: list[dict[str, Any]] = Field(default_factory=list)
    priority_layer: str | None = None

    # Phase 2 tracking
    phase2_triggered: bool = False
    phase2_executed: bool = False
    phase2_hypothesis: str | None = None
    phase2_suspected_devices: list[str] = Field(default_factory=list)
    phase1_findings: list[str] = Field(default_factory=list)
    phase2_findings: list[str] = Field(default_factory=list)

    # Result
    root_cause_found: bool = False
    root_cause: str | None = None
    final_report: str | None = None

    def __init__(self, **data) -> None:
        super().__init__(**data)
        # Initialize all layers
        if not self.layer_coverage:
            self.layer_coverage = {
                layer: LayerStatus(layer=layer)
                for layer in NETWORK_LAYERS
            }

    def get_confidence_gaps(self) -> list[tuple[str, float]]:
        """Find layers with confidence below threshold."""
        gaps = []
        for layer in NETWORK_LAYERS:
            status = self.layer_coverage.get(layer)
            if status and status.confidence < MIN_ACCEPTABLE_CONFIDENCE:
                gaps.append((layer, status.confidence))

        # Sort by confidence (lowest first)
        gaps.sort(key=lambda x: x[1])
        return gaps

    def get_coverage_summary(self) -> str:
        """Generate human-readable coverage summary."""
        lines = ["## Layer Coverage Status\n"]

        for layer in NETWORK_LAYERS:
            status = self.layer_coverage.get(layer)
            if not status:
                continue

            if status.confidence >= MIN_ACCEPTABLE_CONFIDENCE:
                icon = "✅"
            elif status.checked:
                icon = "⚠️"
            else:
                icon = "⬜"

            info = LAYER_INFO[layer]
            lines.append(
                f"{icon} **{layer}** ({info['name']}): {status.confidence*100:.0f}% confidence, "
                f"{len(status.findings)} findings"
            )

        return "\n".join(lines)

    def should_continue(self) -> bool:
        """Determine if more investigation is needed."""
        if self.root_cause_found:
            return False

        if self.current_round >= self.max_rounds:
            return False

        gaps = self.get_confidence_gaps()
        return len(gaps) > 0


class ExpertModeSupervisor:
    """Supervisor that orchestrates multi-step fault diagnosis.

    The Supervisor:
    1. Round 0: Query KB + Syslog to narrow fault scope
    2. Round 1+: Check L1-L4 layers based on confidence gaps
    3. Assign tasks to QuickAnalyzer
    4. Track findings and determine root cause

    Usage:
        supervisor = ExpertModeSupervisor()
        state = supervisor.create_initial_state("R1 无法与 R2 建立 BGP")

        while state.should_continue():
            task = await supervisor.plan_next_task(state)
            result = await quick_analyzer.execute(task)
            state = supervisor.update_state(state, result)

        report = supervisor.generate_report(state)
    """

    def __init__(self, max_rounds: int = 5) -> None:
        """Initialize supervisor.

        Args:
            max_rounds: Maximum investigation rounds.
        """
        self.max_rounds = max_rounds

    def create_initial_state(
        self,
        query: str,
        path_devices: list[str] | None = None,
    ) -> SupervisorState:
        """Create initial state for diagnosis.

        Args:
            query: User query or alert message.
            path_devices: Devices to investigate.

        Returns:
            Initial SupervisorState.
        """
        return SupervisorState(
            query=query,
            path_devices=path_devices or [],
            max_rounds=self.max_rounds,
        )

    async def round_zero_context(self, state: SupervisorState) -> SupervisorState:
        """Round 0: Query KB + Syslog to narrow fault scope.

        Args:
            state: Current state.

        Returns:
            Updated state with KB/Syslog context and priority_layer.
        """
        query = state.query

        # Query KB for similar cases
        try:
            from olav.tools.kb_tools import kb_search

            cases = kb_search.invoke({"query": query, "size": 3}) or []
            state.similar_cases = cases

            # Determine priority layer from historical cases
            layer_votes: dict[str, int] = {}
            for case in cases:
                layer = case.get("root_cause_layer", "")
                if layer in NETWORK_LAYERS:
                    layer_votes[layer] = layer_votes.get(layer, 0) + 1

            if layer_votes:
                state.priority_layer = max(layer_votes, key=lambda k: layer_votes[k])
                logger.info(f"KB suggests priority layer: {state.priority_layer}")
        except Exception as e:
            logger.warning(f"KB search failed: {e}")

        # Query Syslog for recent events
        try:
            from olav.tools.opensearch_tool import SyslogSearchTool

            syslog_tool = SyslogSearchTool()
            events = await syslog_tool.execute(
                query=query,
                hours_ago=24,
                size=10,
            )

            if events and hasattr(events, "data"):
                state.syslog_events = events.data or []
        except Exception as e:
            logger.warning(f"Syslog search failed: {e}")

        return state

    async def plan_next_task(self, state: SupervisorState) -> DiagnosisTask | None:
        """Plan next diagnosis task based on confidence gaps.

        Args:
            state: Current state.

        Returns:
            Next DiagnosisTask or None if investigation complete.
        """
        if not state.should_continue():
            return None

        # Get layers needing investigation
        gaps = state.get_confidence_gaps()
        if not gaps:
            return None

        # Prioritize based on KB suggestion or lowest confidence
        target_layer = gaps[0][0]  # Default: lowest confidence

        if state.priority_layer and state.priority_layer in [g[0] for g in gaps]:
            target_layer = state.priority_layer

        # Create task
        layer_info = LAYER_INFO[target_layer]
        task = DiagnosisTask(
            task_id=state.current_round + 1,
            layer=target_layer,
            description=f"Investigate {target_layer} ({layer_info['name']}) for: {state.query}",
            suggested_tables=layer_info["suzieq_tables"],
            suggested_filters={"hostname": state.path_devices} if state.path_devices else {},
            priority="high" if target_layer == state.priority_layer else "medium",
        )

        state.current_task = task
        return task

    def update_state(
        self,
        state: SupervisorState,
        result: DiagnosisResult,
    ) -> SupervisorState:
        """Update state with QuickAnalyzer result.

        Args:
            state: Current state.
            result: Result from QuickAnalyzer.

        Returns:
            Updated state.
        """
        # Update layer coverage
        layer = result.layer
        if layer in state.layer_coverage:
            status = state.layer_coverage[layer]
            status.update(result.confidence, result.findings)

        # Collect Phase 1 findings for potential Phase 2
        state.phase1_findings.extend(result.findings)

        # Check for root cause indicators
        if result.findings:
            # Simple heuristic: high-confidence findings might be root cause
            if result.confidence >= 0.8:
                critical_keywords = ["down", "failed", "error", "mismatch", "异常", "故障"]
                for finding in result.findings:
                    if any(kw in finding.lower() for kw in critical_keywords):
                        state.root_cause_found = True
                        state.root_cause = finding
                        break

        # Increment round
        state.current_round += 1
        state.current_task = None

        return state

    def should_trigger_phase2(self, state: SupervisorState) -> bool:
        """Determine if Phase 2 (Deep Analyzer) is needed.

        Phase 2 triggers when:
        1. Phase 1 confidence is insufficient (<80%)
        2. Suspected issues found but root cause not confirmed
        3. Query involves configuration policies (SuzieQ blind spot)
        4. Phase 1 data may be stale

        Args:
            state: Current SupervisorState after Phase 1.

        Returns:
            True if Phase 2 should be executed.
        """
        # Already found root cause with high confidence
        if state.root_cause_found:
            # Even if root cause found, check if it's policy-related
            # which requires Phase 2 confirmation
            if state.root_cause:
                policy_keywords = ["route-map", "prefix-list", "acl", "policy", "策略"]
                if any(kw in state.root_cause.lower() for kw in policy_keywords):
                    logger.info("Phase 2 needed: root cause is policy-related, needs confirmation")
                    return True
            return False

        # Check max Phase 1 confidence
        max_confidence = 0.0
        for layer_status in state.layer_coverage.values():
            max_confidence = max(max_confidence, layer_status.confidence)

        # Trigger 1: Confidence below threshold
        if max_confidence < 0.80:
            logger.info(f"Phase 2 needed: max confidence {max_confidence:.2f} < 0.80")
            return True

        # Trigger 2: Suspected issues but no confirmed root cause
        if state.phase1_findings and not state.root_cause_found:
            logger.info("Phase 2 needed: findings exist but no confirmed root cause")
            return True

        # Trigger 3: Query involves policy keywords (SuzieQ blind spot)
        policy_keywords = ["route-map", "prefix-list", "acl", "policy", "策略", "过滤"]
        query_lower = state.query.lower()
        if any(kw in query_lower for kw in policy_keywords):
            logger.info("Phase 2 needed: query involves routing policy")
            return True

        # Trigger 4: Check if findings suggest policy issues
        for finding in state.phase1_findings:
            finding_lower = finding.lower()
            # Missing routes often indicate policy blocking
            if "missing" in finding_lower and "route" in finding_lower:
                logger.info("Phase 2 needed: missing routes may indicate policy issue")
                return True
            # No route to destination
            if "no route" in finding_lower or "路由缺失" in finding_lower:
                logger.info("Phase 2 needed: route missing, check policy")
                return True

        return False

    def prepare_phase2_context(self, state: SupervisorState) -> SupervisorState:
        """Prepare context for Phase 2 execution.

        Builds hypothesis and identifies suspected devices from Phase 1 findings.

        Args:
            state: SupervisorState after Phase 1.

        Returns:
            Updated state with Phase 2 context.
        """
        state.phase2_triggered = True

        # Build hypothesis from findings
        hypothesis_parts = []
        suspected_devices = set(state.path_devices)

        for finding in state.phase1_findings[-10:]:  # Last 10 findings
            # Extract device names
            import re
            device_matches = re.findall(r"\b(R\d+|SW\d+|S\d+)\b", finding)
            suspected_devices.update(device_matches)

            # Check for policy hints
            if any(kw in finding.lower() for kw in ["missing", "route", "bgp", "no path"]):
                hypothesis_parts.append(finding)

        # Generate hypothesis
        if hypothesis_parts:
            state.phase2_hypothesis = (
                f"Phase 1 发现: {'; '.join(hypothesis_parts[:3])}. "
                f"假设: 可能存在 BGP route-map/prefix-list 配置阻断路由传递。"
            )
        else:
            state.phase2_hypothesis = (
                "Phase 1 未能确认根因。需要检查设备实时配置验证假设。"
            )

        state.phase2_suspected_devices = list(suspected_devices)

        logger.info(f"Phase 2 context prepared: hypothesis={state.phase2_hypothesis[:100]}...")
        logger.info(f"Phase 2 suspected devices: {state.phase2_suspected_devices}")

        return state

    def generate_report(self, state: SupervisorState) -> str:
        """Generate final diagnosis report.

        Args:
            state: Final state.

        Returns:
            Formatted diagnosis report.
        """
        lines = [
            "# 🔍 Fault Diagnosis Report\n",
            f"**Query**: {state.query}\n",
            f"**Devices**: {', '.join(state.path_devices) if state.path_devices else 'N/A'}\n",
            f"**Rounds**: {state.current_round}/{state.max_rounds}\n",
            "",
            state.get_coverage_summary(),
            "",
        ]

        # Root cause section
        if state.root_cause_found:
            lines.extend([
                "## 🎯 Root Cause\n",
                f"**{state.root_cause}**\n",
                "",
            ])
        else:
            lines.extend([
                "## ⚠️ Root Cause Not Identified\n",
                "Further investigation may be needed.\n",
                "",
            ])

        # Findings by layer
        lines.append("## 📋 Findings by Layer\n")
        for layer in NETWORK_LAYERS:
            status = state.layer_coverage.get(layer)
            if status and status.findings:
                lines.append(f"### {layer} ({LAYER_INFO[layer]['name']})\n")
                for finding in status.findings:
                    lines.append(f"- {finding}")
                lines.append("")

        # KB context
        if state.similar_cases:
            lines.extend([
                "## 📚 Similar Historical Cases\n",
            ])
            for case in state.similar_cases[:3]:
                lines.append(f"- {case.get('fault_description', 'N/A')}")
            lines.append("")

        state.final_report = "\n".join(lines)
        return state.final_report
