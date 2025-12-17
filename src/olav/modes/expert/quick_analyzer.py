"""Expert Mode Quick Analyzer - ReAct agent for layer investigation.

The Quick Analyzer:
1. Receives tasks from Supervisor
2. Uses ReAct pattern with SuzieQ tools
3. Executes targeted queries
4. Returns findings to Supervisor

This is the "worker" in the Supervisor-Worker pattern.
"""

import logging
from typing import Any

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from olav.core.llm import LLMFactory
from olav.core.prompt_manager import prompt_manager
from olav.modes.expert.supervisor import (
    LAYER_INFO,
    SUZIEQ_MAX_CONFIDENCE,
    DiagnosisResult,
    DiagnosisTask,
)
from olav.modes.shared.debug import DebugContext

logger = logging.getLogger(__name__)


# =============================================================================
# Quick Analyzer
# =============================================================================


class QuickAnalyzer:
    """ReAct agent for targeted layer investigation.

    Uses SuzieQ tools to query network state and analyze findings.

    Usage:
        analyzer = QuickAnalyzer()
        task = DiagnosisTask(
            task_id=1,
            layer="L3",
            description="Check BGP state on R1",
            suggested_tables=["bgp", "routes"],
        )
        result = await analyzer.execute(task)
    """

    def __init__(
        self,
        max_iterations: int = 5,
        debug_context: DebugContext | None = None,
    ) -> None:
        """Initialize Quick Analyzer.

        Args:
            max_iterations: Maximum ReAct iterations per task.
            debug_context: Optional debug context for instrumentation.
        """
        self.max_iterations = max_iterations
        self.debug_context = debug_context
        self.llm = LLMFactory.get_chat_model()

    def _get_suzieq_tools(self) -> list[Any]:
        """Get SuzieQ tools for querying.

        Returns:
            List of LangChain tools for Parquet-based network data queries.

        Note:
            Only includes tools that work with Parquet files directly.
            SuzieQ library-dependent tools (path_trace, health_check, topology)
            are excluded as SuzieQ library is not installed.
        """
        tools = []

        # Basic query tools (Parquet-based, no SuzieQ library needed)
        try:
            from olav.tools.suzieq_tool import (
                create_suzieq_query_tool,
                create_suzieq_schema_tool,
            )
            tools.extend([
                create_suzieq_query_tool(),
                create_suzieq_schema_tool(),
            ])
        except ImportError:
            logger.warning("SuzieQ basic tools not available")

        # Note: suzieq_path_trace, suzieq_health_check, suzieq_topology_analyze
        # require the SuzieQ library to be installed. Since we only have Parquet
        # files, we rely on suzieq_query + manual path tracing methodology.

        if not tools:
            logger.warning("No SuzieQ tools available, using mock")

        return tools

    def _get_available_tables_desc(self) -> str:
        """Get description of available SuzieQ tables.

        Returns:
            Formatted table descriptions.
        """
        lines = []
        for layer, info in LAYER_INFO.items():
            tables = info["suzieq_tables"]
            if tables:
                lines.append(f"- {layer}: {', '.join(tables)}")
        return "\n".join(lines) if lines else "No tables available"

    async def execute(self, task: DiagnosisTask) -> DiagnosisResult:
        """Execute a diagnosis task using ReAct pattern.

        Args:
            task: Task from Supervisor.

        Returns:
            DiagnosisResult with findings.
        """
        layer_info = LAYER_INFO.get(task.layer, {})

        # Load prompt from config
        system_prompt = prompt_manager.load_prompt(
            "modes/expert",
            "quick_analyzer",
            layer=task.layer,
            layer_name=layer_info.get("name", "Unknown"),
            task_description=task.description,
            suggested_tables=", ".join(task.suggested_tables),
            available_tables=self._get_available_tables_desc(),
        )

        # Build prompt template
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="messages"),
        ])

        # Get tools
        tools = self._get_suzieq_tools()

        # If no tools available, return mock result
        if not tools:
            return DiagnosisResult(
                task_id=task.task_id,
                layer=task.layer,
                success=False,
                confidence=0.0,
                findings=["SuzieQ tools not available"],
                error="Tools not configured",
            )

        # Create ReAct agent using LangGraph (modern approach)
        try:
            from langchain_core.messages import SystemMessage
            from langgraph.errors import GraphRecursionError
            from langgraph.prebuilt import create_react_agent

            # Build input message with explicit tool usage instructions
            system_msg = """You are a network diagnostics expert. Your task is to investigate network issues.

IMPORTANT: You MUST use the available tools to gather data before providing any analysis.
STOP IMMEDIATELY once you have enough data to identify the root cause. Do NOT keep querying indefinitely.

## Available Tools

- **suzieq_schema_search**: Search for available tables and fields (use once at start)
- **suzieq_query**: Query network data from tables (routes, interfaces, vlan, arpnd, macs, lldp)

## Connectivity Diagnosis Methodology

When diagnosing "Device A cannot access Device B" (e.g., "PC1 on SW1 E0/1 cannot access IOT device on SW2 E0/2"):

### Step 1: Identify the endpoints (2-3 queries max)
Query interfaces to find the VLAN and IP configuration:
```
suzieq_query(table="interfaces", hostname="SW1")  # Find E0/1's VLAN
suzieq_query(table="interfaces", hostname="SW2")  # Find E0/2's VLAN
```

### Step 2: Find the gateway devices
Query vlan table to understand the L3 gateway:
```
suzieq_query(table="vlan")  # Find SVI interfaces for each VLAN
```

### Step 3: Check routing on the gateway (CRITICAL)
Query the gateway's route table:
```
suzieq_query(table="routes", hostname="GATEWAY_DEVICE")
```
Look for:
- Is there a route to the destination subnet?
- Is the next-hop reachable?
- Are there any routing issues (no route, blackhole, asymmetric routing)?

### Step 4: Report root cause
Based on the data, identify:
- **Missing route**: Gateway lacks route to destination network
- **Interface down**: L1/L2 issue blocking connectivity
- **VLAN mismatch**: Endpoints on wrong VLANs
- **ARP issue**: No ARP entry for gateway

## Key Tables
- **routes**: Routing table (prefix, nexthop, vrf)
- **interfaces**: Interface status, IP, VLAN assignment
- **vlan**: VLAN configuration and SVI mapping
- **arpnd**: ARP/ND table entries

## IMPORTANT Rules
1. Make 5-8 targeted queries maximum, then STOP and provide findings
2. Focus on the specific devices mentioned in the query
3. Always check the gateway's route table for connectivity issues
4. Once you identify a likely root cause, STOP and report it
"""

            input_msg = f"Investigate {task.layer} ({layer_info.get('name', '')}): {task.description}"
            if task.suggested_filters.get("hostname"):
                input_msg += f"\nDevices to check: {task.suggested_filters['hostname']}"

            logger.debug(f"QuickAnalyzer input: {input_msg}")
            logger.debug(f"QuickAnalyzer tools: {[t.name for t in tools]}")

            # Create agent graph with system message
            agent = create_react_agent(self.llm, tools)

            # Collect tool outputs and messages
            tool_outputs = []
            output = ""
            collected_messages = []

            # Use streaming with updates mode to collect results even on recursion limit
            input_messages = [
                SystemMessage(content=system_msg),
                ("user", input_msg),
            ]

            try:
                # Stream with updates mode - more reliable for collecting tool outputs
                async for chunk in agent.astream(
                    {"messages": input_messages},
                    config={"recursion_limit": 20},
                    stream_mode="updates",
                ):
                    # Each chunk contains node updates
                    # Format: {"node_name": {"messages": [...]}}
                    for _node_name, node_data in chunk.items():
                        if "messages" in node_data:
                            for msg in node_data["messages"]:
                                collected_messages.append(msg)
                                msg_type = type(msg).__name__

                                # Extract tool outputs from ToolMessage
                                if msg_type == "ToolMessage":
                                    tool_content = getattr(msg, "content", "")
                                    if isinstance(tool_content, str):
                                        try:
                                            import json
                                            parsed = json.loads(tool_content)
                                            if isinstance(parsed, dict):
                                                tool_outputs.append(parsed)
                                        except (json.JSONDecodeError, ValueError):
                                            # Raw string output
                                            if len(tool_content) > 50:
                                                tool_outputs.append({"raw": tool_content[:2000]})
                                    elif isinstance(tool_content, dict):
                                        tool_outputs.append(tool_content)

            except GraphRecursionError:
                # Recursion limit hit - expected for complex queries
                logger.warning(f"QuickAnalyzer hit recursion limit - extracting partial results from {len(tool_outputs)} tool outputs")

            # Extract AI message output from collected messages
            for msg in reversed(collected_messages):
                msg_type = type(msg).__name__
                if msg_type == "AIMessage" and hasattr(msg, "content"):
                    content = msg.content
                    if content and not content.startswith("Sorry"):
                        output = content
                        break

            logger.debug(f"QuickAnalyzer collected {len(tool_outputs)} tool outputs, {len(collected_messages)} messages")
            logger.debug(f"QuickAnalyzer output: {output[:500] if output else 'EMPTY'}")

            # Parse findings from both text output and tool outputs
            findings = self._parse_findings(output)

            # Extract meaningful findings from tool data
            findings.extend(self._extract_findings_from_tool_data(tool_outputs))

            confidence = self._estimate_confidence(findings)
            if tool_outputs and not findings:
                # If we got tool outputs but no findings, set minimum confidence
                confidence = max(confidence, 0.3)
                findings = ["Data retrieved from network devices (no specific issues identified)"]

            return DiagnosisResult(
                task_id=task.task_id,
                layer=task.layer,
                success=True,
                confidence=confidence,
                findings=findings,
                tool_outputs=tool_outputs if tool_outputs else [{"raw_output": output}],
            )
        except Exception as e:
            logger.error(f"QuickAnalyzer execution failed: {e}")
            return DiagnosisResult(
                task_id=task.task_id,
                layer=task.layer,
                success=False,
                confidence=0.0,
                findings=[],
                error=str(e),
            )

    def _parse_findings(self, output: str) -> list[str]:
        """Parse findings from agent output.

        Args:
            output: Raw agent output.

        Returns:
            List of finding strings.
        """
        findings = []

        # Simple parsing: look for bullet points or numbered items
        lines = output.split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Skip metadata lines
            if line.startswith(("Thought:", "Action:")):
                continue

            # Capture bullet points or significant statements
            if line.startswith(("- ", "* ")):
                findings.append(line[2:])
            elif any(kw in line.lower() for kw in ["down", "failed", "error", "anomaly", "fault"]):
                findings.append(line)

        return findings[:10]  # Limit to 10 findings

    def _extract_findings_from_tool_data(self, tool_outputs: list[dict]) -> list[str]:
        """Extract meaningful findings from tool output data.

        Analyzes SuzieQ query results to identify:
        - Interface status (up/down)
        - VLAN configurations
        - Route information
        - Device connectivity

        Args:
            tool_outputs: List of tool output dictionaries.

        Returns:
            List of finding strings.
        """
        findings = []

        for tool_data in tool_outputs:
            if not isinstance(tool_data, dict):
                continue

            # Handle raw string output
            if "raw" in tool_data:
                raw = tool_data["raw"]
                if isinstance(raw, str) and len(raw) > 50:
                    # Look for key patterns in raw output
                    if "hostname" in raw.lower():
                        findings.append(f"Device data retrieved: {raw[:200]}...")
                continue

            # Handle structured SuzieQ output
            data = tool_data.get("data", [])
            source = tool_data.get("source", "tool")
            metadata = tool_data.get("metadata", {})
            table = metadata.get("table", "unknown")

            if not isinstance(data, list) or not data:
                continue

            # Analyze based on table type
            if table == "interfaces":
                # Look for interface issues
                down_interfaces = [
                    d for d in data
                    if d.get("state") == "down" or d.get("adminState") == "down"
                ]
                if down_interfaces:
                    for iface in down_interfaces[:3]:
                        findings.append(
                            f"Interface DOWN: {iface.get('hostname', '?')}/{iface.get('ifname', '?')} "
                            f"(state={iface.get('state', '?')})"
                        )

                # Extract device IPs
                for d in data[:5]:
                    if d.get("ipAddressList"):
                        ips = d.get("ipAddressList", [])
                        if ips:
                            findings.append(
                                f"Device {d.get('hostname', '?')} {d.get('ifname', '?')}: "
                                f"IP {ips[0] if isinstance(ips, list) else ips}"
                            )

            elif table == "routes":
                # Summarize routing info
                findings.append(f"Route table: {len(data)} routes from {source}")
                # Look for default routes
                defaults = [d for d in data if d.get("prefix") == "0.0.0.0/0"]
                if defaults:
                    for route in defaults[:2]:
                        findings.append(
                            f"Default route on {route.get('hostname', '?')}: "
                            f"via {route.get('nexthopIps', route.get('nexthop', '?'))}"
                        )

            elif table in ("vlan", "vlans"):
                # VLAN configuration
                findings.append(f"VLAN config: {len(data)} VLANs found")
                for vlan in data[:3]:
                    findings.append(
                        f"VLAN {vlan.get('vlan', '?')} on {vlan.get('hostname', '?')}: "
                        f"{vlan.get('interfaces', vlan.get('state', 'active'))}"
                    )

            else:
                # Generic summary
                device = tool_data.get("device", "unknown")
                findings.append(f"[{source}/{table}] {len(data)} records from {device}")

        return findings[:15]  # Limit findings

    def _estimate_confidence(self, findings: list[str]) -> float:
        """Estimate confidence based on findings.

        Args:
            findings: List of finding strings.

        Returns:
            Confidence score (0.0 - SUZIEQ_MAX_CONFIDENCE).
        """
        if not findings:
            return 0.0

        # More findings = higher confidence (up to SuzieQ cap)
        base_confidence = min(len(findings) * 0.1, 0.4)

        # Critical findings boost confidence
        critical_keywords = ["down", "failed", "error", "anomaly", "fault"]
        critical_count = sum(
            1 for f in findings
            if any(kw in f.lower() for kw in critical_keywords)
        )

        critical_boost = min(critical_count * 0.1, 0.2)

        return min(base_confidence + critical_boost, SUZIEQ_MAX_CONFIDENCE)
