# OLAV - Supervisor-Driven Deep Dive Workflow
# New architecture: Supervisor tracks L1-L4 confidence, Quick Analyzer executes via ReAct

"""
Supervisor-Driven Deep Dive Workflow

This is a simplified refactoring of the original deep_dive.py that:
1. Removes static Checklist YAML (over-engineering)
2. Uses Supervisor to dynamically generate check tasks
3. Tracks L1-L4 confidence with code-enforced structure
4. Quick Analyzer uses ReAct with SuzieQ tools

Architecture:
    Alert/Query → Supervisor (tracks L1-L4 confidence) ↔ Quick Analyzer (ReAct)

Key Design Decisions:
- No static checklists - Supervisor dynamically decides what to check
- Code-enforced layer coverage - cannot forget any layer
- Confidence gaps drive investigation - not predefined checklist order
- Quick Analyzer can "be lazy" - Supervisor detects and compensates
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import create_react_agent

from olav.core.llm import LLMFactory
from olav.core.prompt_manager import prompt_manager
from config.settings import settings

logger = logging.getLogger(__name__)


# =============================================================================
# Constants - Loaded from config/prompts/contexts/osi_layers.yaml
# =============================================================================


def _load_osi_layer_config() -> dict[str, Any]:
    """Load OSI layer configuration from YAML file.

    Returns:
        Dict containing layers, thresholds, and layer_order configuration.
    """
    # Resolve config path relative to project root
    config_path = Path(__file__).parents[3] / "config" / "prompts" / "contexts" / "osi_layers.yaml"

    if not config_path.exists():
        logger.warning(f"OSI layer config not found at {config_path}, using defaults")
        return {}

    with config_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


# Load configuration at module level (cached)
_OSI_CONFIG = _load_osi_layer_config()

# Network layer identifiers
NETWORK_LAYERS = tuple(_OSI_CONFIG.get("layer_order", ["L1", "L2", "L3", "L4"]))

# Layer metadata (name, description, suzieq_tables, keywords)
LAYER_INFO = _OSI_CONFIG.get("layers", {})

# Confidence thresholds
MIN_ACCEPTABLE_CONFIDENCE = settings.deepdive_min_confidence
SUZIEQ_MAX_CONFIDENCE = settings.deepdive_suzieq_max_confidence
REALTIME_CONFIDENCE = settings.deepdive_realtime_confidence


# =============================================================================
# State Types
# =============================================================================


class LayerStatus:
    """Status tracking for a single network layer.

    This is a class (not TypedDict) to provide helper methods.
    """

    def __init__(
        self,
        checked: bool = False,
        confidence: float = 0.0,
        findings: list[str] | None = None,
        last_checked: str | None = None,
    ) -> None:
        self.checked = checked
        self.confidence = confidence
        self.findings = findings or []
        self.last_checked = last_checked

    def update(self, new_confidence: float, new_findings: list[str]) -> None:
        """Update layer with new check results."""
        self.checked = True
        # Keep highest confidence seen
        self.confidence = max(self.confidence, new_confidence)
        self.findings.extend(new_findings)
        self.last_checked = datetime.now().isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "checked": self.checked,
            "confidence": self.confidence,
            "findings": self.findings,
            "last_checked": self.last_checked,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LayerStatus:
        return cls(
            checked=data.get("checked", False),
            confidence=data.get("confidence", 0.0),
            findings=data.get("findings", []),
            last_checked=data.get("last_checked"),
        )

    def __repr__(self) -> str:
        return f"LayerStatus(checked={self.checked}, confidence={self.confidence:.0%}, findings={len(self.findings)})"


class SupervisorDrivenState(dict):
    """LangGraph-compatible state for Supervisor-Driven workflow.

    Key principle: layer_coverage is code-enforced to have all 4 layers.
    Supervisor cannot "forget" to track any layer.

    Attributes:
        messages: Conversation history
        query: Original user query or alert
        path_devices: Devices on the fault path
        layer_coverage: L1-L4 status tracking (always has all 4 keys)
        current_round: Current iteration number
        max_rounds: Maximum iterations (default 5)
        current_task: Task description for Quick Analyzer
        current_layer: Which layer is being checked
        root_cause_found: Whether root cause has been identified
        root_cause: Description of root cause
        final_report: Final diagnosis report

        Round 0 Context (Supervisor uses RAG and Syslog to narrow fault scope):
        similar_cases: Historical cases from KB (Agentic RAG)
        syslog_events: Related syslog events (fault trigger identification)
        priority_layer: Layer suggested by KB/Syslog analysis (priority investigation layer)

        Investigation Tracking:
        investigation_steps: Step-by-step investigation process log
        workflow_start_time: Timestamp when workflow started
    """

    # Type annotations for LangGraph
    messages: Annotated[list[BaseMessage], add_messages]
    query: str
    path_devices: list[str]
    layer_coverage: dict[str, dict[str, Any]]  # Serialized LayerStatus
    current_round: int
    max_rounds: int
    current_task: str | None
    current_layer: str | None
    root_cause_found: bool
    root_cause: str | None
    final_report: str | None
    # Round 0 Context (Supervisor decision basis)
    similar_cases: list[dict[str, Any]]  # KB search results
    syslog_events: list[dict[str, Any]]  # Syslog search results
    priority_layer: str | None  # Layer suggested by KB/Syslog
    # Investigation Tracking
    investigation_steps: list[str]  # Step-by-step log
    workflow_start_time: str | None  # ISO timestamp


def create_initial_state(
    query: str,
    path_devices: list[str] | None = None,
    max_rounds: int = 5,
) -> SupervisorDrivenState:
    """Create initial state with all layers initialized to 0% confidence.

    Args:
        query: User query or alert message
        path_devices: Devices to investigate
        max_rounds: Maximum investigation rounds

    Returns:
        Initial state dictionary
    """
    return SupervisorDrivenState(
        messages=[HumanMessage(content=query)],
        query=query,
        path_devices=path_devices or [],
        layer_coverage={
            layer: LayerStatus().to_dict() for layer in NETWORK_LAYERS
        },
        current_round=0,
        max_rounds=max_rounds,
        current_task=None,
        current_layer=None,
        root_cause_found=False,
        root_cause=None,
        final_report=None,
        # Round 0 Context (initialized empty, filled by supervisor_node)
        similar_cases=[],
        syslog_events=[],
        priority_layer=None,
        # Investigation Tracking
        investigation_steps=[f"Workflow started: {query}"],
        workflow_start_time=datetime.now().isoformat(),
    )


# =============================================================================
# Helper Functions
# =============================================================================


def get_confidence_gaps(
    layer_coverage: dict[str, dict[str, Any]],
    threshold: float = MIN_ACCEPTABLE_CONFIDENCE,
) -> list[tuple[str, float]]:
    """Find layers with confidence below threshold.

    Args:
        layer_coverage: Current layer status dict
        threshold: Minimum acceptable confidence

    Returns:
        List of (layer_name, confidence) tuples, sorted by confidence ascending
    """
    gaps = []
    for layer in NETWORK_LAYERS:
        status = layer_coverage.get(layer, {})
        confidence = status.get("confidence", 0.0)
        if confidence < threshold:
            gaps.append((layer, confidence))

    # Sort by confidence (lowest first - needs most attention)
    gaps.sort(key=lambda x: x[1])
    return gaps


def get_coverage_summary(layer_coverage: dict[str, dict[str, Any]]) -> str:
    """Generate human-readable coverage summary.

    Args:
        layer_coverage: Current layer status dict

    Returns:
        Formatted summary string
    """
    lines = ["## Layer Coverage Status\n"]

    for layer in NETWORK_LAYERS:
        status = layer_coverage.get(layer, {})
        confidence = status.get("confidence", 0.0)
        checked = status.get("checked", False)
        findings_count = len(status.get("findings", []))

        if confidence >= MIN_ACCEPTABLE_CONFIDENCE:
            icon = "✅"
        elif checked:
            icon = "⚠️"
        else:
            icon = "⬜"

        info = LAYER_INFO[layer]
        lines.append(
            f"{icon} **{layer}** ({info['name']}): {confidence*100:.0f}% confidence, "
            f"{findings_count} findings"
        )

    return "\n".join(lines)


def should_continue_investigation(state: SupervisorDrivenState) -> bool:
    """Determine if more investigation is needed.

    Returns False if:
    - Root cause found
    - Max rounds reached
    - All layers have sufficient confidence
    """
    if state.get("root_cause_found", False):
        return False

    if state.get("current_round", 0) >= state.get("max_rounds", 5):
        return False

    layer_coverage = state.get("layer_coverage", {})
    gaps = get_confidence_gaps(layer_coverage)

    return len(gaps) > 0


# =============================================================================
# Workflow Nodes
# =============================================================================


async def supervisor_node(state: SupervisorDrivenState) -> dict:
    """Supervisor: Analyze KB/Syslog for context, then assign check tasks.

    Round 0 Strategy (narrow fault scope):
    1. Query KB for similar historical cases (Agentic RAG)
    2. Query Syslog for recent fault events (trigger identification)
    3. Use KB/Syslog results to suggest priority_layer

    Subsequent Rounds:
    1. Check layer_coverage for confidence gaps
    2. Consider priority_layer if KB/Syslog suggested one
    3. Generate check task for Quick Analyzer

    Returns:
        Updated state with current_task, current_layer, and Round 0 context
    """
    layer_coverage = state.get("layer_coverage", {})
    current_round = state.get("current_round", 0)
    query = state.get("query", "")
    path_devices = state.get("path_devices", [])

    # === Round 0: KB + Syslog Search for Fault Scope Narrowing ===
    similar_cases_list: list[dict] = []
    syslog_events_list: list[dict] = []
    priority_layer: str | None = None
    kb_section = ""
    syslog_section = ""

    if current_round == 0:
        # --- Agentic RAG: Query KB for similar cases ---
        try:
            from olav.tools.kb_tools import kb_search

            # kb_search is sync tool, run it directly (not awaited)
            similar_cases_list = kb_search.invoke({
                "query": query,
                "size": 3,
            }) or []

            if similar_cases_list:
                hints = ["## 📚 Similar Historical Cases\n"]
                layer_votes: dict[str, int] = {}  # Track layer frequency
                for case in similar_cases_list:
                    layer = case.get("root_cause_layer", "")
                    if layer and layer in NETWORK_LAYERS:
                        layer_votes[layer] = layer_votes.get(layer, 0) + 1
                    hints.append(f"- **{case.get('fault_description', 'N/A')}**")
                    hints.append(f"  - Root Cause: {case.get('root_cause', 'N/A')}")
                    hints.append(f"  - Layer: {layer or 'N/A'}")
                    hints.append(f"  - Confidence: {case.get('confidence', 0)*100:.0f}%")
                    hints.append("")
                kb_section = "\n".join(hints)

                # Set priority layer from KB voting
                if layer_votes:
                    priority_layer = max(layer_votes, key=layer_votes.get)  # type: ignore
                    logger.info(f"🎯 KB suggests priority layer: {priority_layer}")

                logger.info(f"🔍 Found {len(similar_cases_list)} similar cases in KB")
        except Exception as e:
            logger.warning(f"KB search failed (non-critical): {e}")

        # --- Syslog: Query for recent fault events ---
        try:
            from olav.tools.syslog_tool import syslog_search

            # Build syslog query from user query and path devices
            # Build syslog keyword from path devices
            syslog_keyword = "DOWN|ERROR|BGP|OSPF|NEIGHBOR|LINK"
            if path_devices:
                # Add device names as additional keywords
                syslog_keyword = f"{syslog_keyword}|{'|'.join(path_devices)}"

            # syslog_search is async tool, use await
            syslog_result = await syslog_search.ainvoke({
                "keyword": syslog_keyword,
                "start_time": "now-1h",  # Look back 1 hour for recent events
                "limit": 10,
            })

            # Extract events from result
            if isinstance(syslog_result, dict) and syslog_result.get("success"):
                syslog_events_list = syslog_result.get("data", []) or []
            else:
                syslog_events_list = []

            if syslog_events_list:
                event_hints = ["## 📋 Recent Syslog Events\n"]
                for event in syslog_events_list[:5]:  # Show top 5
                    timestamp = event.get("@timestamp", event.get("timestamp", "N/A"))
                    host = event.get("host", event.get("hostname", "N/A"))
                    message = event.get("message", "")[:100]  # Truncate
                    severity = event.get("severity", event.get("level", "N/A"))
                    event_hints.append(f"- [{timestamp}] **{host}** ({severity})")
                    event_hints.append(f"  {message}")
                    event_hints.append("")
                syslog_section = "\n".join(event_hints)

                # Analyze syslog for layer hints
                syslog_text = " ".join(e.get("message", "") for e in syslog_events_list)
                syslog_lower = syslog_text.lower()

                if not priority_layer:  # Only if KB didn't set one
                    if "bgp" in syslog_lower or "ospf" in syslog_lower or "neighbor" in syslog_lower:
                        priority_layer = "L3_ROUTING"
                    elif "link" in syslog_lower or "down" in syslog_lower or "interface" in syslog_lower:
                        priority_layer = "L1_PHYSICAL"
                    elif "vlan" in syslog_lower or "stp" in syslog_lower or "spanning" in syslog_lower:
                        priority_layer = "L2_DATALINK"
                    elif "qos" in syslog_lower or "queue" in syslog_lower or "congestion" in syslog_lower:
                        priority_layer = "L4_TRANSPORT"

                    if priority_layer:
                        logger.info(f"🎯 Syslog suggests priority layer: {priority_layer}")

                logger.info(f"📋 Found {len(syslog_events_list)} syslog events")
        except Exception as e:
            logger.warning(f"Syslog search failed (non-critical): {e}")

    # Find confidence gaps
    gaps = get_confidence_gaps(layer_coverage)

    if not gaps:
        # All layers have sufficient confidence
        return {
            "current_task": None,
            "current_layer": None,
            "messages": [AIMessage(content="All layers have sufficient confidence. Generating report...")],
        }

    # Layer selection strategy:
    # 1. If priority_layer from KB/Syslog is in gaps, use it
    # 2. Otherwise, pick the layer with lowest confidence
    target_layer, current_confidence = gaps[0]  # Default: lowest confidence

    if priority_layer:
        # Check if priority_layer is in the gaps list
        for layer, conf in gaps:
            if layer == priority_layer:
                target_layer = layer
                current_confidence = conf
                logger.info(f"🎯 Using KB/Syslog priority layer: {target_layer}")
                break

    layer_info = LAYER_INFO[target_layer]

    # Generate check task with KB/Syslog context
    devices_str = ", ".join(path_devices) if path_devices else "all devices"
    tables_str = ", ".join(layer_info["suzieq_tables"]) if layer_info["suzieq_tables"] else "N/A (may need CLI)"

    # Include KB/Syslog context in task for Quick Analyzer
    context_section = ""
    if current_round == 0 and (similar_cases_list or syslog_events_list):
        context_parts = []
        if similar_cases_list:
            cases_summary = "; ".join(
                f"{c.get('fault_description', 'N/A')[:50]} (Layer: {c.get('root_cause_layer', 'N/A')})"
                for c in similar_cases_list[:2]
            )
            context_parts.append(f"**Similar Cases**: {cases_summary}")
        if syslog_events_list:
            events_summary = "; ".join(
                f"{e.get('message', '')[:40]}" for e in syslog_events_list[:2]
            )
            context_parts.append(f"**Recent Events**: {events_summary}")
        if context_parts:
            context_section = "\n**KB/Syslog Context**:\n" + "\n".join(context_parts) + "\n"

    task_description = f"""## Check Task: {target_layer} - {layer_info['name']}

**Current Confidence**: {current_confidence*100:.0f}%
**Target Devices**: {devices_str}
**Suggested SuzieQ Tables**: {tables_str}
{context_section}
**Layer Description**: {layer_info['description']}

**Original Query**: {query}

Please investigate this layer and report:
1. What you checked (tables, queries)
2. Key findings (issues or normal status)
3. Your confidence level (0-100%)

Remember: Always call suzieq_schema_search first to discover available fields.
"""

    # Generate status message
    coverage_summary = get_coverage_summary(layer_coverage)

    # Include KB/Syslog sections on first round
    round0_context = ""
    if current_round == 0:
        if kb_section:
            round0_context += f"\n{kb_section}\n"
        if syslog_section:
            round0_context += f"\n{syslog_section}\n"

    priority_note = ""
    if priority_layer and target_layer == priority_layer:
        priority_note = f"\n> 📍 **Priority**: KB/Syslog analysis suggests starting with {priority_layer}.\n"

    msg = f"""## 🎯 Supervisor Decision (Round {current_round + 1})

{coverage_summary}
{round0_context}{priority_note}
### Next Action
Investigating **{target_layer}** ({layer_info['name']}) - currently at {current_confidence*100:.0f}% confidence.
"""

    # Build return dict with Round 0 context
    investigation_steps = state.get("investigation_steps", [])
    step_msg = f"Round {current_round + 1}: Supervisor assigned {target_layer} ({layer_info['name']}) investigation"
    if priority_layer and target_layer == priority_layer:
        step_msg += " (priority from KB/Syslog)"

    result: dict[str, Any] = {
        "current_task": task_description,
        "current_layer": target_layer,
        "current_round": current_round + 1,
        "investigation_steps": investigation_steps + [step_msg],
        "messages": [AIMessage(content=msg)],
    }

    # Store KB/Syslog results in state (only on Round 0)
    if current_round == 0:
        result["similar_cases"] = similar_cases_list
        result["syslog_events"] = syslog_events_list
        result["priority_layer"] = priority_layer

    return result


async def quick_analyzer_node(state: SupervisorDrivenState) -> dict:
    """Quick Analyzer: Execute check task using ReAct with SuzieQ/Nornir tools.

    This node:
    1. Takes the current_task from Supervisor (includes KB/Syslog context)
    2. Uses ReAct pattern with SuzieQ + Nornir tools ONLY
    3. Returns findings and confidence for the current_layer

    Note: KB and Syslog tools are used by Supervisor (Round 0) for scope narrowing.
          Quick Analyzer focuses on data collection and verification.

    Returns:
        Updated state with layer_coverage updated
    """
    current_task = state.get("current_task")
    current_layer = state.get("current_layer")
    layer_coverage = state.get("layer_coverage", {})

    if not current_task or not current_layer:
        return {"messages": [AIMessage(content="No task to execute.")]}

    # 明确要求必须做实时验证
    realtime_prompt = """
重要：你必须在历史数据（SuzieQ）分析后，调用 CLI/NETCONF 工具（cli_show 或 netconf_get）对关键结论进行实时验证。只有在实时验证后，置信度才能超过60%。否则请继续深入，直到完成实时验证。
"""
    # 拼接到原始任务
    if realtime_prompt not in current_task:
        current_task = f"{current_task}\n\n{realtime_prompt}"

    from olav.tools.nornir_tool import cli_show, netconf_get
    from olav.tools.suzieq_analyzer_tool import (
        suzieq_health_check,
        suzieq_schema_search,
        suzieq_query,
        suzieq_path_trace,
        suzieq_topology_analyze,
    )
    tools = [
        suzieq_schema_search,
        suzieq_query,
        suzieq_health_check,
        suzieq_path_trace,
        suzieq_topology_analyze,
        cli_show,
        netconf_get,
    ]

    llm = LLMFactory.get_chat_model(reasoning=True)
    react_agent = create_react_agent(llm, tools)
    result = await react_agent.ainvoke({
        "input": current_task,
        "messages": state.get("messages", []),
    })

    # 检查是否用过 CLI/NETCONF
    cli_used = any(
        "cli_show" in str(msg) or "netconf_get" in str(msg)
        for msg in result.get("messages", [])
    )
    # 置信度上限逻辑
    max_confidence = REALTIME_CONFIDENCE if cli_used else SUZIEQ_MAX_CONFIDENCE

    # Extract findings and confidence from agent response
    final_message = result["messages"][-1].content if result["messages"] else ""

    # Parse confidence from response (look for percentage)
    import re
    confidence_match = re.search(r"(\d+)\s*%", final_message)
    if confidence_match:
        confidence = min(int(confidence_match.group(1)) / 100, max_confidence)
    else:
        # Default to 50% if no explicit confidence given
        confidence = 0.50

    # Extract findings (lines starting with - or •)
    findings = []
    for line in final_message.split("\n"):
        line = line.strip()
        if line.startswith(("-", "•", "*", "⚠️", "❌", "✅")):
            findings.append(line.lstrip("-•* "))

    if not findings:
        findings = [f"Layer {current_layer} checked. See details above."]

    # Update layer coverage
    layer_status = LayerStatus.from_dict(layer_coverage.get(current_layer, {}))
    layer_status.update(confidence, findings)
    layer_coverage[current_layer] = layer_status.to_dict()

    # Generate response message
    msg = f"""## 📊 Quick Analyzer Result: {current_layer}

**Confidence**: {confidence*100:.0f}%
**Findings** ({len(findings)}):
{chr(10).join(f"- {f}" for f in findings[:10])}

{get_coverage_summary(layer_coverage)}
"""

    # Add investigation step
    investigation_steps = state.get("investigation_steps", [])
    findings_summary = "; ".join(findings[:3]) if findings else "No issues found"
    step_msg = f"{current_layer} analyzed: {confidence*100:.0f}% confidence - {findings_summary[:100]}"

    return {
        "layer_coverage": layer_coverage,
        "current_task": None,  # Clear task
        "investigation_steps": investigation_steps + [step_msg],
        "messages": [AIMessage(content=msg)],
    }


async def report_generator_node(state: SupervisorDrivenState) -> dict:
    """Generate final diagnosis report with structured DiagnosisReport.

    This node:
    1. Correlates all findings across layers
    2. Uses LLM to identify root cause
    3. Creates structured DiagnosisReport
    4. Indexes to knowledge base (Agentic RAG)
    5. Returns Markdown report
    """
    from olav.models.diagnosis_report import (
        DeviceSummary,
        DiagnosisReport,
        extract_layers,
        extract_protocols,
        extract_tags_from_text,
    )
    from olav.tools.kb_tools import kb_index_report

    query = state.get("query", "")
    layer_coverage = state.get("layer_coverage", {})
    path_devices = state.get("path_devices", [])

    # Collect all findings by layer
    layer_findings: dict[str, list[str]] = {}
    all_findings_text = []

    for layer in NETWORK_LAYERS:
        status = layer_coverage.get(layer, {})
        findings = status.get("findings", [])
        layer_findings[layer] = findings
        if findings:
            all_findings_text.append(f"### {layer} ({LAYER_INFO[layer]['name']})")
            all_findings_text.extend(f"- {f}" for f in findings)

    findings_text = "\n".join(all_findings_text) if all_findings_text else "No significant findings."

    # Use LLM to identify root cause (structured output)
    # Root cause analysis needs reasoning for complex thinking
    llm = LLMFactory.get_chat_model(reasoning=True)

    root_cause_prompt = f"""Analyze the following network diagnosis findings and identify the root cause.

## Original Query
{query}

## Layer Coverage
{get_coverage_summary(layer_coverage)}

## Detailed Findings
{findings_text}

## Task
Analyze findings and provide a device-centric root cause analysis.

Format your response EXACTLY as:
ROOT_CAUSE: [One sentence describing the primary issue]
DEVICE: [Device name, e.g., R1, SW1, or "Unknown"]
INTERFACE: [Interface name if applicable, e.g., GigabitEthernet0/0, or "N/A"]
LAYER: [L1/L2/L3/L4 or "Unknown"]
CONFIDENCE: [0-100]
AFFECTED_DEVICES: [Comma-separated list of all devices with issues, e.g., "R1, R2"]
EVIDENCE:
- [Device:Interface] Finding 1
- [Device:Interface] Finding 2
RECOMMENDED_ACTION: [Specific remediation step]
"""

    response = await llm.ainvoke([SystemMessage(content=root_cause_prompt)])
    response_text = response.content

    # Parse LLM response
    import re

    root_cause = "Unable to determine root cause"
    root_cause_device = None
    root_cause_layer = None
    root_cause_interface = None
    affected_devices = []
    confidence = 0.5
    evidence_chain = []
    recommended_action = ""

    # Extract fields from structured response
    if match := re.search(r"ROOT_CAUSE:\s*(.+?)(?=\n[A-Z_]+:|$)", response_text, re.DOTALL):
        root_cause = match.group(1).strip()

    if match := re.search(r"DEVICE:\s*(.+?)(?=\n|$)", response_text):
        device = match.group(1).strip()
        if device.lower() != "unknown":
            root_cause_device = device

    if match := re.search(r"INTERFACE:\s*(.+?)(?=\n|$)", response_text):
        iface = match.group(1).strip()
        if iface.lower() not in ("n/a", "unknown", "none"):
            root_cause_interface = iface

    if match := re.search(r"AFFECTED_DEVICES:\s*(.+?)(?=\n|$)", response_text):
        devices_str = match.group(1).strip()
        affected_devices = [d.strip() for d in devices_str.split(",") if d.strip()]

    if match := re.search(r"LAYER:\s*(L[1-4])", response_text):
        root_cause_layer = match.group(1)

    if match := re.search(r"CONFIDENCE:\s*(\d+)", response_text):
        confidence = min(int(match.group(1)) / 100, 1.0)

    if match := re.search(r"EVIDENCE:\s*\n((?:[-•*]\s*.+\n?)+)", response_text):
        evidence_text = match.group(1)
        evidence_chain = [
            line.lstrip("-•* ").strip()
            for line in evidence_text.strip().split("\n")
            if line.strip()
        ]

    if match := re.search(r"RECOMMENDED_ACTION:\s*(.+?)(?=\n[A-Z_]+:|$)", response_text, re.DOTALL):
        recommended_action = match.group(1).strip()

    # Build device summaries from affected_devices and layer_findings
    device_summaries = {}
    all_devices = set(affected_devices) | set(path_devices)
    if root_cause_device:
        all_devices.add(root_cause_device)

    for device in all_devices:
        is_root = device == root_cause_device
        device_summaries[device] = DeviceSummary(
            device=device,
            status="faulty" if is_root else ("degraded" if device in affected_devices else "healthy"),
            layer_findings=layer_findings,
            confidence=confidence if is_root else 0.5,
        )

    # Include interface in root cause if available
    if root_cause_interface and root_cause_device:
        root_cause = f"{root_cause} (Interface: {root_cause_interface})"

    # Extract metadata
    combined_text = f"{root_cause} {recommended_action} {' '.join(evidence_chain)}"
    tags = extract_tags_from_text(combined_text)
    protocols = extract_protocols(combined_text)
    affected_layers_list = extract_layers(layer_findings)

    # Calculate duration
    workflow_start_time = state.get("workflow_start_time")
    duration_seconds = 0.0
    if workflow_start_time:
        try:
            start_dt = datetime.fromisoformat(workflow_start_time)
            duration_seconds = (datetime.now() - start_dt).total_seconds()
        except Exception:
            pass

    # Get investigation steps
    investigation_steps = state.get("investigation_steps", [])
    investigation_steps.append(f"Root cause identified: {root_cause[:80]}")
    investigation_steps.append(f"Report generated with {confidence*100:.0f}% confidence")

    # Create structured report
    report = DiagnosisReport(
        fault_description=query,
        source=path_devices[0] if path_devices else (root_cause_device if root_cause_device else None),
        destination=path_devices[-1] if len(path_devices) > 1 else None,
        fault_path=list(all_devices) if all_devices else [],
        root_cause=root_cause,
        root_cause_device=root_cause_device,
        root_cause_layer=root_cause_layer,
        confidence=confidence,
        evidence_chain=evidence_chain,
        device_summaries=device_summaries,
        recommended_action=recommended_action,
        tags=tags,
        affected_protocols=protocols,
        affected_layers=affected_layers_list,
        investigation_process=investigation_steps,
        duration_seconds=duration_seconds,
    )

    # Generate detailed Markdown report (with investigation process)
    markdown_report = report.render_detailed_markdown()
    report.markdown_content = markdown_report

    # Save to local file
    try:
        report_path = report.save()
        logger.info(f"📁 Report saved to: {report_path}")
        markdown_report += f"\n\n---\n📁 *Report saved to: `{report_path}`*"
    except Exception as e:
        logger.error(f"Failed to save report to file: {e}")

    # Index to knowledge base (Agentic RAG)
    try:
        indexed = await kb_index_report(report)
        if indexed:
            logger.info(f"✅ Report {report.report_id} indexed to knowledge base")
            markdown_report += f"\n📚 *Report indexed to knowledge base: `{report.report_id}`*"
        else:
            logger.warning(f"⚠️ Failed to index report {report.report_id}")
    except Exception as e:
        logger.error(f"Error indexing report: {e}")

    return {
        "final_report": markdown_report,
        "root_cause_found": True,
        "root_cause": root_cause,
        "investigation_steps": investigation_steps,
        "messages": [AIMessage(content=markdown_report)],
    }


# =============================================================================
# Parallel Device Inspection (Using Send)
# =============================================================================


async def parallel_device_inspection_node(state: SupervisorDrivenState) -> dict:
    """Dispatch parallel device inspections using Send().

    This node is used when there are multiple devices to inspect.
    It dispatches individual device inspections in parallel.

    Returns:
        List of Send() commands for each device
    """
    from langgraph.constants import Send

    path_devices = state.get("path_devices", [])
    query = state.get("query", "")
    layer_coverage = state.get("layer_coverage", {})

    if len(path_devices) <= 1:
        # Single device - use regular quick_analyzer
        return {
            "messages": [AIMessage(content="Single device - proceeding with standard analysis.")],
        }

    # Find which layers need investigation
    gaps = get_confidence_gaps(layer_coverage)
    layers_to_check = [layer for layer, _ in gaps] if gaps else list(NETWORK_LAYERS)

    # Generate Send commands for parallel inspection
    sends = []
    for device in path_devices:
        sends.append(
            Send(
                "device_inspector",
                {
                    "device": device,
                    "context": query,
                    "layers_to_check": layers_to_check,
                    "known_issues": [],
                },
            )
        )

    msg = f"""## 🔀 Parallel Device Inspection

Dispatching parallel inspections to **{len(path_devices)}** devices:
{chr(10).join(f'- {d}' for d in path_devices)}

Layers to check: {', '.join(layers_to_check)}
"""

    return {
        "parallel_sends": sends,
        "messages": [AIMessage(content=msg)],
    }


async def device_inspector_node(state: dict) -> dict:
    """Individual device inspector node (for Send() pattern).

    This node receives state for a single device and performs inspection.
    Results are aggregated by the aggregator node.
    """
    from olav.workflows.device_inspector import inspect_device

    device = state.get("device", "unknown")
    context = state.get("context", "")
    layers_to_check = state.get("layers_to_check", list(NETWORK_LAYERS))
    known_issues = state.get("known_issues", [])

    # Run device inspection
    result = await inspect_device(
        device=device,
        context=context,
        layers_to_check=layers_to_check,
        known_issues=known_issues,
    )

    return {
        "device_result": result,
        "device": device,
    }


async def aggregator_node(state: SupervisorDrivenState) -> dict:
    """Aggregate results from parallel device inspections.

    This node collects results from all device_inspector nodes
    and updates the layer_coverage with combined findings.
    """
    # Get results from parallel inspections
    # In LangGraph, parallel results are collected automatically
    device_results = state.get("device_results", [])
    layer_coverage = state.get("layer_coverage", {}).copy()

    if not device_results:
        return {
            "messages": [AIMessage(content="No device results to aggregate.")],
        }

    # Aggregate findings by layer
    aggregated_findings: dict[str, list[str]] = {layer: [] for layer in NETWORK_LAYERS}
    aggregated_confidence: dict[str, list[float]] = {layer: [] for layer in NETWORK_LAYERS}

    for result in device_results:
        if not result.get("success", False):
            continue

        summary = result.get("summary", {})
        layer_findings = summary.get("layer_findings", {})

        for layer in NETWORK_LAYERS:
            findings = layer_findings.get(layer, [])
            if findings:
                device_name = result.get("device", "unknown")
                for finding in findings:
                    aggregated_findings[layer].append(f"[{device_name}] {finding}")

        # Track confidence per device
        confidence = summary.get("confidence", 0.0)
        for layer in NETWORK_LAYERS:
            aggregated_confidence[layer].append(confidence)

    # Update layer_coverage with aggregated results
    for layer in NETWORK_LAYERS:
        status = LayerStatus.from_dict(layer_coverage.get(layer, {}))

        # Add new findings
        status.findings.extend(aggregated_findings[layer])

        # Update confidence (average of device confidences)
        if aggregated_confidence[layer]:
            avg_conf = sum(aggregated_confidence[layer]) / len(aggregated_confidence[layer])
            status.confidence = max(status.confidence, avg_conf)

        status.checked = True
        status.last_checked = datetime.now().isoformat()
        layer_coverage[layer] = status.to_dict()

    # Generate summary message
    total_findings = sum(len(f) for f in aggregated_findings.values())
    successful_devices = sum(1 for r in device_results if r.get("success", False))

    msg = f"""## 📊 Parallel Inspection Aggregation

**Devices inspected**: {successful_devices}/{len(device_results)}
**Total findings**: {total_findings}

### Findings by Layer
"""
    for layer in NETWORK_LAYERS:
        findings = aggregated_findings[layer]
        if findings:
            msg += f"\n**{layer}**: {len(findings)} findings"
            for f in findings[:3]:  # First 3
                msg += f"\n  - {f}"
            if len(findings) > 3:
                msg += f"\n  - (+{len(findings) - 3} more)"

    return {
        "layer_coverage": layer_coverage,
        "messages": [AIMessage(content=msg)],
    }


def routing_function(state: SupervisorDrivenState) -> Literal["quick_analyzer", "report"]:
    """Route between Quick Analyzer and Report Generator."""
    if should_continue_investigation(state):
        return "quick_analyzer"
    return "report"


# =============================================================================
# Workflow Builder
# =============================================================================


def create_supervisor_driven_workflow(checkpointer=None):
    """Create the Supervisor-Driven Deep Dive workflow.

    Graph structure:
        START → supervisor → routing_function
                              ↓ "quick_analyzer"    ↓ "report"
                         quick_analyzer         report_generator → END
                              ↓
                         supervisor (loop)

    Args:
        checkpointer: LangGraph checkpointer for state persistence

    Returns:
        Compiled LangGraph workflow
    """
    workflow = StateGraph(SupervisorDrivenState)

    # Add nodes
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("quick_analyzer", quick_analyzer_node)
    workflow.add_node("report", report_generator_node)

    # Define edges
    workflow.set_entry_point("supervisor")

    # Supervisor routes to either quick_analyzer or report
    workflow.add_conditional_edges(
        "supervisor",
        routing_function,
        {
            "quick_analyzer": "quick_analyzer",
            "report": "report",
        },
    )

    # Quick Analyzer always goes back to Supervisor
    workflow.add_edge("quick_analyzer", "supervisor")

    # Report is terminal
    workflow.add_edge("report", END)

    return workflow.compile(checkpointer=checkpointer)


# =============================================================================
# Workflow Class Wrapper (for Registry integration)
# =============================================================================


from olav.workflows.base import BaseWorkflow
from olav.workflows.registry import WorkflowRegistry


@WorkflowRegistry.register(
    name="supervisor_driven_deep_dive",
    description="Intelligent deep diagnostics: Supervisor tracks L1-L4 confidence, Quick Analyzer uses ReAct for checks",
    examples=[
        "Deep analyze why R1 BGP is down",
        "Diagnose packet loss between SW1 and SW2",
        "Troubleshoot the root cause of network failure",
        "L1 to L4 full-layer diagnosis",
        "Interface error rate is high, help analyze the cause",
        "Intelligent troubleshooting: route flapping",
        "Trace the root cause",
    ],
    triggers=[
        r"deep.*analyz",
        r"root.*cause",
        r"troubleshoot.*fault",
        r"intelligent.*diagnos",
        r"L[1-4].*diagnos",
        r"full.*layer.*check",
    ],
)
class SupervisorDrivenWorkflow(BaseWorkflow):
    """Supervisor-Driven Deep Dive Workflow.

    This is the new dynamic architecture that replaces static checklists.

    Key features:
    - Supervisor tracks L1-L4 confidence levels
    - Quick Analyzer executes checks using ReAct + SuzieQ tools
    - Confidence gaps drive investigation (not predefined order)
    - Terminates when all layers have sufficient confidence or max rounds reached
    """

    def __init__(self, checkpointer=None) -> None:
        self.checkpointer = checkpointer
        self._graph = None

    @property
    def name(self) -> str:
        return "supervisor_driven_deep_dive"

    @property
    def description(self) -> str:
        return "Intelligent deep diagnostics (Supervisor + Quick Analyzer)"

    @property
    def tools_required(self) -> list[str]:
        """List of tools required by this workflow.

        Returns:
            List of tool identifiers used in SupervisorDrivenWorkflow.
            Includes both SuzieQ (historical, 60% confidence) and
            Nornir (real-time, 95% confidence) tools for funnel debugging.
        """
        return [
            # Tier 1: SuzieQ - Historical data analysis (60% max confidence)
            "suzieq_schema_search",
            "suzieq_query",
            "suzieq_health_check",
            "suzieq_path_trace",
            "suzieq_topology_analyze",
            # Tier 2: Nornir - Real-time verification (95% confidence)
            "cli_show",
            "netconf_get",
        ]

    async def validate_input(self, user_query: str) -> tuple[bool, str]:
        """Validate if user query is suitable for SupervisorDrivenWorkflow.

        Args:
            user_query: Raw user input

        Returns:
            Tuple of (is_valid, reason)
        """
        # SupervisorDrivenWorkflow is designed for complex diagnostics
        # that require multi-step analysis and layer-based investigation
        if not user_query or len(user_query.strip()) < 5:
            return False, "Query too short for deep dive analysis"

        # Check for diagnostic keywords
        diagnostic_keywords = [
            # English
            "why", "diagnose", "analyze", "check", "problem",
            "issue", "fail", "slow", "down", "not working",
            "troubleshoot", "fault", "error", "root cause",
        ]

        query_lower = user_query.lower()
        if any(kw in query_lower for kw in diagnostic_keywords):
            return True, "Query matches diagnostic pattern"

        # Allow any query in expert mode (user explicitly requested)
        return True, "Expert mode accepts all queries"

    def build_graph(self, checkpointer=None):
        """Build the LangGraph workflow.

        Args:
            checkpointer: Optional checkpointer override. If not provided,
                         uses self.checkpointer from constructor.

        Returns:
            Compiled StateGraph ready for execution
        """
        # Use provided checkpointer or fall back to instance checkpointer
        cp = checkpointer if checkpointer is not None else self.checkpointer
        if self._graph is None:
            self._graph = create_supervisor_driven_workflow(cp)
        return self._graph

    async def run(self, query: str, path_devices: list[str] | None = None, **kwargs):
        """Execute the workflow.

        Args:
            query: User query or alert
            path_devices: Devices to investigate
            **kwargs: Additional config (thread_id, etc.)

        Returns:
            Final state with diagnosis report
        """
        graph = self.build_graph()
        initial_state = create_initial_state(query, path_devices=path_devices)

        config = {}
        if "thread_id" in kwargs:
            config["configurable"] = {"thread_id": kwargs["thread_id"], "checkpoint_ns": ""}

        return await graph.ainvoke(initial_state, config)


def create_parallel_supervisor_workflow(checkpointer=None):
    """Create a workflow with parallel device inspection using Send().

    This is an enhanced version of the Supervisor-Driven workflow that
    uses LangGraph's Send() to dispatch parallel device inspections when
    multiple devices are involved.

    Graph structure:
        START → supervisor → routing_function
                              ↓ "parallel"          ↓ "quick_analyzer"    ↓ "report"
                    parallel_dispatch          quick_analyzer         report → END
                         ↓ (Send)                    ↓
                   device_inspector(s)           supervisor (loop)
                         ↓
                    aggregator
                         ↓
                     supervisor

    Args:
        checkpointer: LangGraph checkpointer for state persistence

    Returns:
        Compiled LangGraph workflow with parallel capability
    """
    from langgraph.constants import Send

    def parallel_routing_function(
        state: SupervisorDrivenState,
    ) -> Literal["parallel", "quick_analyzer", "report"]:
        """Enhanced routing that can dispatch parallel inspections."""
        path_devices = state.get("path_devices", [])
        current_round = state.get("current_round", 0)

        # Use parallel inspection on first round with multiple devices
        if current_round == 0 and len(path_devices) > 1:
            return "parallel"

        # Otherwise use standard routing
        if should_continue_investigation(state):
            return "quick_analyzer"
        return "report"

    def dispatch_parallel(state: SupervisorDrivenState) -> list:
        """Generate Send() commands for parallel device inspection."""
        path_devices = state.get("path_devices", [])
        query = state.get("query", "")
        layer_coverage = state.get("layer_coverage", {})

        gaps = get_confidence_gaps(layer_coverage)
        layers_to_check = [layer for layer, _ in gaps] if gaps else list(NETWORK_LAYERS)

        return [
            Send(
                "device_inspector",
                {
                    "device": device,
                    "context": query,
                    "layers_to_check": layers_to_check,
                    "known_issues": [],
                },
            )
            for device in path_devices
        ]

    workflow = StateGraph(SupervisorDrivenState)

    # Add nodes
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("quick_analyzer", quick_analyzer_node)
    workflow.add_node("report", report_generator_node)
    workflow.add_node("device_inspector", device_inspector_node)
    workflow.add_node("aggregator", aggregator_node)

    # Define edges
    workflow.set_entry_point("supervisor")

    # Supervisor routes to parallel, quick_analyzer, or report
    workflow.add_conditional_edges(
        "supervisor",
        parallel_routing_function,
        {
            "parallel": "device_inspector",  # Will use Send() via dispatch
            "quick_analyzer": "quick_analyzer",
            "report": "report",
        },
    )

    # Device inspector results go to aggregator
    workflow.add_edge("device_inspector", "aggregator")

    # Aggregator goes back to supervisor
    workflow.add_edge("aggregator", "supervisor")

    # Quick Analyzer goes back to Supervisor
    workflow.add_edge("quick_analyzer", "supervisor")

    # Report is terminal
    workflow.add_edge("report", END)

    return workflow.compile(checkpointer=checkpointer)


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "LAYER_INFO",
    "MIN_ACCEPTABLE_CONFIDENCE",
    # Constants
    "NETWORK_LAYERS",
    "SUZIEQ_MAX_CONFIDENCE",
    # State
    "LayerStatus",
    "SupervisorDrivenState",
    "SupervisorDrivenWorkflow",
    "aggregator_node",
    "create_initial_state",
    "create_parallel_supervisor_workflow",
    # Workflow
    "create_supervisor_driven_workflow",
    "device_inspector_node",
    # Helpers
    "get_confidence_gaps",
    "get_coverage_summary",
    "parallel_device_inspection_node",
    "quick_analyzer_node",
    "report_generator_node",
    "should_continue_investigation",
    # Nodes
    "supervisor_node",
]
