# OLAV - Device Inspector Sub-Graph
# Per-device ReAct agent that outputs DeviceSummary

"""
Device Inspector: Per-Device Investigation Agent

This module provides a focused sub-graph for inspecting a single device.
It uses ReAct pattern with SuzieQ tools and outputs a structured DeviceSummary.

Design:
- Input: device_name, investigation_context (layers to check, known issues)
- Output: DeviceSummary with per-layer findings and confidence
- Uses ReAct with SuzieQ tools for data collection
- Can be run in parallel via LangGraph Send()

Usage:
    from olav.workflows.device_inspector import create_device_inspector, DeviceInspectorInput

    inspector = create_device_inspector()
    result = await inspector.ainvoke({
        "device": "R1",
        "context": "Check L3 routing issues",
        "layers_to_check": ["L3", "L2"],
    })
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated, Any, Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from olav.core.llm import LLMFactory
from olav.models.diagnosis_report import DeviceSummary

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

NETWORK_LAYERS = ("L1", "L2", "L3", "L4")

LAYER_INFO = {
    "L1": {
        "name": "Physical Layer",
        "tables": ["interfaces", "device"],
        "checks": ["interface status", "error counters", "link state"],
    },
    "L2": {
        "name": "Data Link Layer",
        "tables": ["vlan", "macs", "lldp", "stp"],
        "checks": ["VLAN config", "MAC table", "LLDP neighbors", "STP state"],
    },
    "L3": {
        "name": "Network Layer",
        "tables": ["routes", "bgp", "ospf", "arpnd", "address"],
        "checks": ["routing table", "BGP sessions", "OSPF neighbors", "ARP entries"],
    },
    "L4": {
        "name": "Transport Layer",
        "tables": [],
        "checks": ["session state", "NAT entries"],
    },
}


# =============================================================================
# Input/Output Types
# =============================================================================


class DeviceInspectorInput(TypedDict):
    """Input for Device Inspector sub-graph."""
    device: str  # Device name to inspect
    context: str  # Investigation context (what to look for)
    layers_to_check: list[str]  # Which layers to investigate
    known_issues: list[str] | None  # Any known issues to verify


class DeviceInspectorOutput(TypedDict):
    """Output from Device Inspector sub-graph."""
    device: str
    summary: dict[str, Any]  # DeviceSummary.model_dump()
    raw_findings: str  # Full text findings
    success: bool
    error: str | None


# =============================================================================
# State
# =============================================================================


class DeviceInspectorState(TypedDict):
    """State for Device Inspector graph."""
    messages: Annotated[list[BaseMessage], add_messages]
    device: str
    context: str
    layers_to_check: list[str]
    known_issues: list[str]

    # Results
    layer_findings: dict[str, list[str]]  # {layer: [findings]}
    layer_confidence: dict[str, float]  # {layer: confidence}
    overall_status: Literal["healthy", "degraded", "critical", "unknown"]
    inspection_complete: bool


def create_initial_state(
    device: str,
    context: str,
    layers_to_check: list[str] | None = None,
    known_issues: list[str] | None = None,
) -> DeviceInspectorState:
    """Create initial state for device inspection."""
    return DeviceInspectorState(
        messages=[],
        device=device,
        context=context,
        layers_to_check=layers_to_check or list(NETWORK_LAYERS),
        known_issues=known_issues or [],
        layer_findings={layer: [] for layer in NETWORK_LAYERS},
        layer_confidence={layer: 0.0 for layer in NETWORK_LAYERS},
        overall_status="unknown",
        inspection_complete=False,
    )


# =============================================================================
# Nodes
# =============================================================================


async def inspect_node(state: DeviceInspectorState) -> dict:
    """Main inspection node using ReAct with SuzieQ tools.

    This node:
    1. Creates a focused prompt for the specific device
    2. Uses ReAct pattern with SuzieQ tools
    3. Extracts layer-specific findings and confidence
    """
    device = state["device"]
    context = state["context"]
    layers_to_check = state["layers_to_check"]
    known_issues = state.get("known_issues", [])

    # Get SuzieQ tools
    from olav.tools.suzieq_parquet_tool import suzieq_query, suzieq_schema_search
    from olav.tools.suzieq_analyzer_tool import (
        suzieq_health_check,
        suzieq_topology_analyze,
    )

    tools = [
        suzieq_schema_search,
        suzieq_query,
        suzieq_health_check,
        suzieq_topology_analyze,
    ]

    # Build layer-specific instructions
    layer_instructions = []
    for layer in layers_to_check:
        info = LAYER_INFO.get(layer, {})
        tables = info.get("tables", [])
        checks = info.get("checks", [])

        layer_instructions.append(f"""
### {layer} - {info.get('name', layer)}
- SuzieQ Tables: {', '.join(tables) if tables else 'N/A (limited coverage)'}
- Checks to perform: {', '.join(checks)}
""")

    # Build known issues section
    known_issues_section = ""
    if known_issues:
        known_issues_section = f"""
## Known Issues to Verify
{chr(10).join(f'- {issue}' for issue in known_issues)}
"""

    # System prompt for device inspection
    system_prompt = f"""You are a Device Inspector agent focused on investigating device: **{device}**

## Investigation Context
{context}
{known_issues_section}
## Layers to Check
{chr(10).join(layer_instructions)}

## Instructions
1. Start with suzieq_schema_search to discover available fields for each table
2. Use suzieq_query with hostname="{device}" to focus on this specific device
3. For each layer, collect findings and assess confidence level
4. Look for anomalies: down interfaces, missing neighbors, route issues, etc.

## Output Format
After investigation, provide a structured summary:

```
LAYER_FINDINGS:
L1: [finding1, finding2, ...]
L2: [finding1, finding2, ...]
L3: [finding1, finding2, ...]
L4: [finding1, finding2, ...]

LAYER_CONFIDENCE:
L1: 0.XX
L2: 0.XX
L3: 0.XX
L4: 0.XX

OVERALL_STATUS: healthy|degraded|critical
```

Be thorough but efficient. Focus only on device {device}.
"""

    # Create and run ReAct agent
    llm = LLMFactory.get_chat_model()
    react_agent = create_react_agent(llm, tools)

    try:
        result = await react_agent.ainvoke({
            "messages": [
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"Inspect device {device} for the following context: {context}"),
            ],
        })

        # Extract the final message
        final_messages = result.get("messages", [])
        if final_messages:
            final_content = final_messages[-1].content if hasattr(final_messages[-1], 'content') else str(final_messages[-1])
        else:
            final_content = "No results from inspection."

        # Parse findings from response
        layer_findings, layer_confidence, overall_status = parse_inspection_results(final_content)

        return {
            "layer_findings": layer_findings,
            "layer_confidence": layer_confidence,
            "overall_status": overall_status,
            "inspection_complete": True,
            "messages": [AIMessage(content=final_content)],
        }

    except Exception as e:
        logger.error(f"Device inspection failed for {device}: {e}")
        return {
            "layer_findings": {layer: [f"Error: {str(e)}"] for layer in NETWORK_LAYERS},
            "layer_confidence": {layer: 0.0 for layer in NETWORK_LAYERS},
            "overall_status": "unknown",
            "inspection_complete": True,
            "messages": [AIMessage(content=f"Inspection failed: {e}")],
        }


def parse_inspection_results(
    content: str,
) -> tuple[dict[str, list[str]], dict[str, float], str]:
    """Parse structured results from inspector response.

    Returns:
        Tuple of (layer_findings, layer_confidence, overall_status)
    """
    import re

    layer_findings: dict[str, list[str]] = {layer: [] for layer in NETWORK_LAYERS}
    layer_confidence: dict[str, float] = {layer: 0.0 for layer in NETWORK_LAYERS}
    overall_status = "unknown"

    # Parse LAYER_FINDINGS section
    findings_match = re.search(
        r"LAYER_FINDINGS:\s*\n((?:L[1-4]:.+\n?)+)",
        content,
        re.IGNORECASE,
    )
    if findings_match:
        findings_text = findings_match.group(1)
        for layer in NETWORK_LAYERS:
            pattern = rf"{layer}:\s*\[?([^\]\n]+)\]?"
            match = re.search(pattern, findings_text, re.IGNORECASE)
            if match:
                findings_str = match.group(1).strip()
                # Split by comma, clean up
                findings = [
                    f.strip().strip("'\"")
                    for f in findings_str.split(",")
                    if f.strip() and f.strip() not in ("None", "[]", "...")
                ]
                layer_findings[layer] = findings

    # Parse LAYER_CONFIDENCE section
    confidence_match = re.search(
        r"LAYER_CONFIDENCE:\s*\n((?:L[1-4]:.+\n?)+)",
        content,
        re.IGNORECASE,
    )
    if confidence_match:
        confidence_text = confidence_match.group(1)
        for layer in NETWORK_LAYERS:
            pattern = rf"{layer}:\s*(0?\.\d+|\d+(?:\.\d+)?)"
            match = re.search(pattern, confidence_text, re.IGNORECASE)
            if match:
                try:
                    conf = float(match.group(1))
                    layer_confidence[layer] = min(conf if conf <= 1 else conf / 100, 1.0)
                except ValueError:
                    pass

    # Parse OVERALL_STATUS
    status_match = re.search(
        r"OVERALL_STATUS:\s*(healthy|degraded|critical|unknown)",
        content,
        re.IGNORECASE,
    )
    if status_match:
        overall_status = status_match.group(1).lower()

    return layer_findings, layer_confidence, overall_status


async def summary_node(state: DeviceInspectorState) -> dict:
    """Generate DeviceSummary from inspection results."""
    device = state["device"]
    layer_findings = state.get("layer_findings", {})
    layer_confidence = state.get("layer_confidence", {})
    overall_status = state.get("overall_status", "unknown")

    # Calculate average confidence
    confidences = [c for c in layer_confidence.values() if c > 0]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

    # Generate summary message
    msg = f"""## Device Inspection Summary: {device}

**Status**: {overall_status.upper()}
**Confidence**: {avg_confidence*100:.0f}%

### Findings by Layer
"""
    for layer in NETWORK_LAYERS:
        findings = layer_findings.get(layer, [])
        conf = layer_confidence.get(layer, 0.0)
        if findings:
            msg += f"\n**{layer}** ({conf*100:.0f}%): "
            msg += ", ".join(findings[:3])  # First 3 findings
            if len(findings) > 3:
                msg += f" (+{len(findings) - 3} more)"
        else:
            msg += f"\n**{layer}** ({conf*100:.0f}%): No issues found"

    return {
        "messages": [AIMessage(content=msg)],
    }


# =============================================================================
# Graph Builder
# =============================================================================


def create_device_inspector() -> StateGraph:
    """Create the Device Inspector sub-graph.

    Returns:
        Compiled StateGraph for device inspection
    """
    # Build graph
    builder = StateGraph(DeviceInspectorState)

    # Add nodes
    builder.add_node("inspect", inspect_node)
    builder.add_node("summary", summary_node)

    # Define edges
    builder.add_edge(START, "inspect")
    builder.add_edge("inspect", "summary")
    builder.add_edge("summary", END)

    return builder.compile()


async def inspect_device(
    device: str,
    context: str,
    layers_to_check: list[str] | None = None,
    known_issues: list[str] | None = None,
) -> DeviceInspectorOutput:
    """High-level function to inspect a single device.

    Args:
        device: Device name to inspect
        context: Investigation context
        layers_to_check: Optional list of layers to focus on
        known_issues: Optional list of known issues to verify

    Returns:
        DeviceInspectorOutput with results
    """
    inspector = create_device_inspector()

    initial_state = create_initial_state(
        device=device,
        context=context,
        layers_to_check=layers_to_check,
        known_issues=known_issues,
    )

    try:
        result = await inspector.ainvoke(initial_state)

        # Build DeviceSummary
        summary = DeviceSummary(
            device=device,
            status=result.get("overall_status", "unknown"),
            layer_findings=result.get("layer_findings", {}),
            confidence=sum(result.get("layer_confidence", {}).values()) / 4,
            checked_at=datetime.now(timezone.utc).isoformat(),
        )

        # Get raw findings from messages
        messages = result.get("messages", [])
        raw_findings = messages[-1].content if messages else ""

        return DeviceInspectorOutput(
            device=device,
            summary=summary.model_dump(),
            raw_findings=raw_findings,
            success=True,
            error=None,
        )

    except Exception as e:
        logger.error(f"Device inspection failed: {e}")
        return DeviceInspectorOutput(
            device=device,
            summary={},
            raw_findings="",
            success=False,
            error=str(e),
        )


# =============================================================================
# Parallel Inspection Support (for LangGraph Send)
# =============================================================================


class ParallelInspectionInput(BaseModel):
    """Input for parallel device inspection via Send()."""
    devices: list[str] = Field(..., description="List of devices to inspect")
    context: str = Field(..., description="Investigation context")
    layers_to_check: list[str] = Field(
        default_factory=lambda: list(NETWORK_LAYERS),
        description="Layers to check",
    )


async def parallel_inspect_devices(
    devices: list[str],
    context: str,
    layers_to_check: list[str] | None = None,
) -> list[DeviceInspectorOutput]:
    """Inspect multiple devices in parallel using asyncio.gather.

    This is the async-based parallel inspection.
    For LangGraph Send()-based parallelism, use the graph nodes directly.

    Args:
        devices: List of device names
        context: Investigation context
        layers_to_check: Optional layers to focus on

    Returns:
        List of DeviceInspectorOutput for each device
    """
    import asyncio

    tasks = [
        inspect_device(
            device=device,
            context=context,
            layers_to_check=layers_to_check,
        )
        for device in devices
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Convert exceptions to error outputs
    outputs: list[DeviceInspectorOutput] = []
    for device, result in zip(devices, results):
        if isinstance(result, Exception):
            outputs.append(DeviceInspectorOutput(
                device=device,
                summary={},
                raw_findings="",
                success=False,
                error=str(result),
            ))
        else:
            outputs.append(result)

    return outputs
