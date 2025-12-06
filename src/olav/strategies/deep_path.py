"""
Deep Path Strategy - ReAct Agent for hypothesis-driven network diagnostics.

This strategy uses LangGraph's prebuilt ReAct agent pattern for "why" questions
and multi-step troubleshooting scenarios. The agent reasons about the problem,
takes actions (tool calls), and observes results in an iterative loop.

Funnel Debugging (漏斗式排错) Methodology:
- Layer 1: Knowledge Base (episodic memory, OpenConfig schema)
- Layer 2: Cached Telemetry (SuzieQ Parquet)
- Layer 3: Source of Truth (NetBox, Syslog)
- Layer 4: Live Device (NETCONF → CLI fallback)

ReAct Pattern:
- Thought: "BGP neighbor is down, could be connectivity issue"
- Action: suzieq_query(table="bgp", hostname="R1")
- Observation: "state: NotEstd, reason: Connect"
- Thought: "Connect error means TCP failed, check IP reachability"
- Action: suzieq_query(table="routes", hostname="R1")
- ... until confident in root cause

Key Benefits over previous implementation:
- Native LangGraph integration with checkpointing
- Automatic reasoning loop management
- Built-in streaming support
- All funnel layers available as tools

Example Queries:
- "为什么 R1 无法建立 BGP 邻居？"
- "诊断为什么路由表不完整"
- "排查网络丢包问题"
"""

import logging
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from olav.core.prompt_manager import prompt_manager
from olav.tools.base import ToolOutput, ToolRegistry

logger = logging.getLogger(__name__)


# ============================================================================
# LangChain Tool Wrappers (bridge to existing BaseTool implementations)
# ============================================================================


def _load_diagnosis_prompt() -> str:
    """Load diagnosis prompt from config/prompts/."""
    try:
        prompt = prompt_manager.load_prompt(
            "strategies/deep_path",
            "react_diagnosis",
        )
        return prompt
    except Exception as e:
        logger.warning(f"Failed to load react_diagnosis prompt: {e}, using fallback")
        return """You are OLAV, a network diagnostics expert. Use the funnel debugging approach:
Layer 1 (Knowledge): episodic_memory_search, openconfig_schema_search
Layer 2 (Cache): suzieq_query, suzieq_schema_search
Layer 3 (SSOT): netbox_api, syslog_search
Layer 4 (Live): netconf_execute, cli_execute (fallback only)

Diagnose step by step until 80% confident."""


def create_langchain_tools(tool_registry: type[ToolRegistry]) -> list:
    """
    Create LangChain-compatible tools from ToolRegistry.

    Implements the full Funnel Debugging tool set:
    - Layer 1: Knowledge Base (episodic_memory, openconfig_schema)
    - Layer 2: Cached Telemetry (suzieq_query, suzieq_schema)
    - Layer 3: Source of Truth (netbox, syslog)
    - Layer 4: Live Device (netconf, cli)
    """
    tools = []

    # Get all tool instances from registry
    # Layer 1: Knowledge Base
    episodic_tool = tool_registry.get_tool("episodic_memory_search")
    openconfig_tool = tool_registry.get_tool("openconfig_schema_search")

    # Layer 2: Cached Telemetry
    suzieq_tool = tool_registry.get_tool("suzieq_query")
    schema_tool = tool_registry.get_tool("suzieq_schema_search")

    # Layer 3: Source of Truth
    netbox_tool = tool_registry.get_tool("netbox_api")
    netbox_schema_tool = tool_registry.get_tool("netbox_schema_search")
    syslog_tool = tool_registry.get_tool("syslog_search")

    # Layer 4: Live Device
    netconf_tool = tool_registry.get_tool("netconf_execute")
    cli_tool = tool_registry.get_tool("cli_execute")

    # ========== Layer 1: Knowledge Base Tools ==========

    @tool
    async def episodic_memory_search(intent: str, max_results: int = 3) -> str:
        """Search past successful diagnoses for similar issues.

        USE THIS FIRST! Check if we've solved similar problems before.

        Args:
            intent: Description of the issue (e.g., "BGP neighbor down")
            max_results: Maximum results to return

        Returns:
            Historical solutions and their success context
        """
        if not episodic_tool:
            return "Error: episodic_memory_search not available (OpenSearch may not be configured)"

        result: ToolOutput = await episodic_tool.execute(
            intent=intent,
            max_results=max_results,
        )

        if result.error:
            return f"No historical matches found: {result.error}"

        if not result.data:
            return "No similar past issues found in memory"

        return f"Found {len(result.data)} historical matches:\n{result.data}"

    @tool
    async def openconfig_schema_search(intent: str, device_type: str = "network-instance") -> str:
        """Search OpenConfig YANG schema for configuration XPaths.

        Use when you need to find the correct YANG path for device configuration.

        Args:
            intent: What you want to configure (e.g., "BGP AS number", "interface IP")
            device_type: OpenConfig module (network-instance, interfaces, routing-policy)

        Returns:
            Matching XPaths with descriptions and examples
        """
        if not openconfig_tool:
            return "Error: openconfig_schema_search not available"

        result: ToolOutput = await openconfig_tool.execute(
            intent=intent,
            device_type=device_type,
        )

        if result.error:
            return f"Error: {result.error}"

        if not result.data:
            return f"No OpenConfig paths found for '{intent}'"

        return f"Found {len(result.data)} matching XPaths:\n{result.data}"

    # ========== Layer 2: Cached Telemetry Tools ==========

    @tool
    async def suzieq_query(
        table: str,
        method: str = "get",
        hostname: str | None = None,
        namespace: str | None = None,
    ) -> str:
        """Query SuzieQ network state data (cached, fast, non-intrusive).

        Args:
            table: Table name (bgp, routes, interfaces, ospfNbr, ospfIf, arpnd, macs, lldp, device, vlan)
            method: Query method - 'get' for raw data, 'summarize' for aggregated stats
            hostname: Filter by specific device hostname
            namespace: Filter by namespace

        Returns:
            Network state data from SuzieQ Parquet files
        """
        if not suzieq_tool:
            return "Error: suzieq_query tool not available"

        result: ToolOutput = await suzieq_tool.execute(
            table=table,
            method=method,
            hostname=hostname,
            namespace=namespace,
        )

        if result.error:
            return f"Error: {result.error}"

        if isinstance(result.data, list):
            if len(result.data) == 0:
                return f"No data found for table '{table}'" + (f" hostname='{hostname}'" if hostname else "")
            data = result.data[:10] if len(result.data) > 10 else result.data
            return f"Found {len(result.data)} records:\n{data}"

        return str(result.data)

    @tool
    async def suzieq_schema_search(query: str) -> str:
        """Discover available SuzieQ tables and their fields.

        Use when unsure which table contains the data you need.

        Args:
            query: Search term (e.g., 'bgp', 'interface', 'routing', 'neighbor')

        Returns:
            Available tables and their fields matching the query
        """
        if not schema_tool:
            return "Error: suzieq_schema_search tool not available"

        result: ToolOutput = await schema_tool.execute(query=query)

        if result.error:
            return f"Error: {result.error}"

        return str(result.data)

    # ========== Layer 3: Source of Truth Tools ==========

    @tool
    async def netbox_api(
        endpoint: str,
        method: str = "GET",
        params: dict | None = None,
    ) -> str:
        """Query NetBox for device inventory, IPs, and cabling.

        Args:
            endpoint: API endpoint (dcim/devices, ipam/ip-addresses, dcim/cables)
            method: HTTP method (GET)
            params: Query parameters (e.g., {"name": "R1"})

        Returns:
            NetBox API response
        """
        if not netbox_tool:
            return "Error: netbox_api tool not available"

        result: ToolOutput = await netbox_tool.execute(
            endpoint=endpoint,
            method=method,
            params=params or {},
        )

        if result.error:
            return f"Error: {result.error}"

        return str(result.data)

    @tool
    async def netbox_schema_search(query: str) -> str:
        """Discover available NetBox API endpoints and fields.

        Use when unsure which NetBox endpoint contains the data you need.

        Args:
            query: Search term (e.g., 'device', 'interface', 'ip address', 'cable')

        Returns:
            Available API endpoints and their parameters matching the query
        """
        if not netbox_schema_tool:
            return "Error: netbox_schema_search tool not available"

        result: ToolOutput = await netbox_schema_tool.execute(query=query)

        if result.error:
            return f"Error: {result.error}"

        return str(result.data)

    @tool
    async def syslog_search(
        keyword: str,
        device_ip: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        limit: int = 20,
    ) -> str:
        """Search device syslog for events and errors.

        Use after identifying anomaly time window from SuzieQ data.

        Args:
            keyword: Search term (e.g., "BGP", "DOWN", "LINK", "OSPF", "CONFIG")
            device_ip: Filter by device IP address
            start_time: Start time (e.g., "1h ago", "2024-01-01T00:00:00Z")
            end_time: End time
            limit: Maximum results

        Returns:
            Matching syslog entries
        """
        if not syslog_tool:
            return "Error: syslog_search not available (OpenSearch may not have syslog index)"

        result: ToolOutput = await syslog_tool.execute(
            keyword=keyword,
            device_ip=device_ip,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )

        if result.error:
            return f"No syslog entries found: {result.error}"

        if not result.data:
            return f"No syslog entries matching '{keyword}'"

        return f"Found {len(result.data)} syslog entries:\n{result.data}"

    # ========== Layer 4: Live Device Tools ==========

    @tool
    async def netconf_execute(
        hostname: str,
        operation: str = "get-config",
        xpath: str | None = None,
        source: str = "running",
    ) -> str:
        """Execute NETCONF operation on device (OpenConfig preferred).

        Use for configuration details not available in SuzieQ cache.
        Prefer this over cli_execute for OpenConfig-capable devices.

        Args:
            hostname: Target device hostname
            operation: NETCONF operation (get-config, get)
            xpath: XPath filter (use openconfig_schema_search to find paths)
            source: Config source (running, candidate)

        Returns:
            NETCONF response (XML or parsed data)
        """
        if not netconf_tool:
            return "Error: netconf_execute not available (Nornir may not be configured)"

        result: ToolOutput = await netconf_tool.execute(
            hostname=hostname,
            operation=operation,
            xpath=xpath,
            source=source,
        )

        if result.error:
            return f"NETCONF error: {result.error}"

        return str(result.data)

    @tool
    async def cli_execute(hostname: str, command: str) -> str:
        """Execute CLI command on device (FALLBACK ONLY).

        Use ONLY when:
        - Device doesn't support OpenConfig/NETCONF
        - Specific CLI output format is required

        Prefer netconf_execute for OpenConfig-capable devices.

        Args:
            hostname: Target device hostname
            command: CLI command to execute

        Returns:
            Command output from the device
        """
        if not cli_tool:
            return "Error: cli_execute not available (Nornir may not be configured)"

        result: ToolOutput = await cli_tool.execute(
            hostname=hostname,
            command=command,
        )

        if result.error:
            return f"CLI error: {result.error}"

        return str(result.data)

    # Add all available tools (ordered by funnel layer)
    # Layer 1
    if episodic_tool:
        tools.append(episodic_memory_search)
        logger.debug("Added Layer 1 tool: episodic_memory_search")
    if openconfig_tool:
        tools.append(openconfig_schema_search)
        logger.debug("Added Layer 1 tool: openconfig_schema_search")

    # Layer 2
    if suzieq_tool:
        tools.append(suzieq_query)
        logger.debug("Added Layer 2 tool: suzieq_query")
    if schema_tool:
        tools.append(suzieq_schema_search)
        logger.debug("Added Layer 2 tool: suzieq_schema_search")

    # Layer 3
    if netbox_tool:
        tools.append(netbox_api)
        logger.debug("Added Layer 3 tool: netbox_api")
    if netbox_schema_tool:
        tools.append(netbox_schema_search)
        logger.debug("Added Layer 3 tool: netbox_schema_search")
    if syslog_tool:
        tools.append(syslog_search)
        logger.debug("Added Layer 3 tool: syslog_search")

    # Layer 4
    if netconf_tool:
        tools.append(netconf_execute)
        logger.debug("Added Layer 4 tool: netconf_execute")
    if cli_tool:
        tools.append(cli_execute)
        logger.debug("Added Layer 4 tool: cli_execute")

    logger.info(f"Created {len(tools)} LangChain tools for ReAct agent (Funnel Debugging)")
    return tools


# ============================================================================
# DeepPathStrategy - ReAct Agent Implementation
# ============================================================================


class DeepPathStrategy:
    """
    Deep Path execution strategy using LangGraph ReAct agent.

    Implements Funnel Debugging (漏斗式排错) methodology through the
    ReAct (Reasoning + Acting) pattern. The agent autonomously
    decides when to use tools and how to interpret results.

    Tool Layers (priority order):
    1. Knowledge Base: episodic_memory, openconfig_schema
    2. Cached Telemetry: suzieq_query, suzieq_schema
    3. Source of Truth: netbox, syslog
    4. Live Device: netconf (preferred), cli (fallback)

    Attributes:
        llm: Language model for reasoning
        tool_registry: Registry of available tools
        agent: Compiled ReAct agent graph
        max_iterations: Maximum reasoning steps (default: 15)
    """

    def __init__(
        self,
        llm: BaseChatModel,
        tool_registry: type[ToolRegistry],
        max_iterations: int = 15,
        **kwargs: Any,
    ) -> None:
        """
        Initialize Deep Path ReAct agent.

        Args:
            llm: Language model for reasoning
            tool_registry: ToolRegistry class for tool access
            max_iterations: Max agent steps (default: 15, ~5 tool calls)
            **kwargs: Additional configuration (ignored for compatibility)
        """
        self.llm = llm
        self.tool_registry = tool_registry
        self.max_iterations = max_iterations

        # Load prompt from config
        self._system_prompt = _load_diagnosis_prompt()

        # Create LangChain tools from registry (all funnel layers)
        self._tools = create_langchain_tools(tool_registry)

        # Build ReAct agent
        self._agent = self._build_agent()

        logger.info(
            f"DeepPathStrategy (ReAct/Funnel) initialized with {len(self._tools)} tools, "
            f"max_iterations={max_iterations}"
        )

    def _build_agent(self):
        """Build the ReAct agent graph with funnel debugging prompt."""
        return create_react_agent(
            self.llm,
            self._tools,
            prompt=self._system_prompt,
        )

    async def execute(
        self,
        user_query: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Execute Deep Path diagnosis using ReAct agent.

        Args:
            user_query: User's diagnostic question
            context: Optional context (currently unused, for compatibility)

        Returns:
            Dict with 'success', 'conclusion', 'reasoning_trace', 'metadata'
        """
        try:
            # Prepare input
            messages = [HumanMessage(content=user_query)]

            # Execute agent with step limit
            config = {"recursion_limit": self.max_iterations}
            result = await self._agent.ainvoke(
                {"messages": messages},
                config=config,
            )

            # Extract final response
            final_messages = result.get("messages", [])
            conclusion = ""
            reasoning_trace = []
            tool_calls_count = 0

            for msg in final_messages:
                msg_type = type(msg).__name__

                if msg_type == "AIMessage":
                    # Check for tool calls
                    if hasattr(msg, "tool_calls") and msg.tool_calls:
                        for tc in msg.tool_calls:
                            tool_calls_count += 1
                            reasoning_trace.append({
                                "step": tool_calls_count,
                                "type": "tool_call",
                                "tool": tc.get("name", "unknown"),
                                "args": tc.get("args", {}),
                            })
                    # Final conclusion is the last AI message content
                    if msg.content:
                        conclusion = msg.content

                elif msg_type == "ToolMessage":
                    reasoning_trace.append({
                        "step": len(reasoning_trace) + 1,
                        "type": "tool_result",
                        "tool": getattr(msg, "name", "unknown"),
                        "result": str(msg.content)[:200] + "..." if len(str(msg.content)) > 200 else str(msg.content),
                    })

            return {
                "success": True,
                "conclusion": conclusion,
                "reasoning_trace": reasoning_trace,
                "hypotheses_tested": [],  # Not tracked in ReAct pattern
                "metadata": {
                    "strategy": "deep_path",
                    "pattern": "react",
                    "tool_calls": tool_calls_count,
                    "total_messages": len(final_messages),
                },
            }

        except Exception as e:
            logger.exception(f"Deep Path (ReAct) execution failed: {e}")
            return {
                "success": False,
                "reason": "exception",
                "error": str(e),
                "reasoning_trace": [],
            }

    async def execute_stream(
        self,
        user_query: str,
        context: dict[str, Any] | None = None,
    ):
        """
        Execute Deep Path diagnosis with streaming output.

        Yields events as the agent reasons through the problem,
        providing real-time visibility into the diagnostic process.

        Args:
            user_query: User's diagnostic question
            context: Optional context

        Yields:
            Dict events with 'type' and relevant data:
            - {"type": "thinking", "content": "..."}
            - {"type": "tool_call", "tool": "...", "args": {...}}
            - {"type": "tool_result", "tool": "...", "result": "..."}
            - {"type": "conclusion", "content": "..."}
        """
        try:
            messages = [HumanMessage(content=user_query)]
            config = {"recursion_limit": self.max_iterations}

            # Stream agent execution
            async for event in self._agent.astream_events(
                {"messages": messages},
                config=config,
                version="v2",
            ):
                event_type = event.get("event", "")

                # Handle different event types
                if event_type == "on_chat_model_start":
                    yield {
                        "type": "thinking",
                        "content": "Analyzing problem...",
                    }

                elif event_type == "on_chat_model_stream":
                    # Streaming token from LLM
                    chunk = event.get("data", {}).get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        yield {
                            "type": "token",
                            "content": chunk.content,
                        }

                elif event_type == "on_tool_start":
                    tool_name = event.get("name", "unknown")
                    tool_input = event.get("data", {}).get("input", {})
                    yield {
                        "type": "tool_call",
                        "tool": tool_name,
                        "args": tool_input,
                    }
                    logger.info(f"ReAct tool call: {tool_name}({tool_input})")

                elif event_type == "on_tool_end":
                    tool_name = event.get("name", "unknown")
                    tool_output = event.get("data", {}).get("output", "")
                    # Truncate long outputs
                    output_str = str(tool_output)
                    if len(output_str) > 500:
                        output_str = output_str[:500] + "..."
                    yield {
                        "type": "tool_result",
                        "tool": tool_name,
                        "result": output_str,
                    }

                elif event_type == "on_chain_end":
                    # Check if this is the final result
                    output = event.get("data", {}).get("output", {})
                    if isinstance(output, dict) and "messages" in output:
                        messages = output["messages"]
                        if messages:
                            last_msg = messages[-1]
                            if hasattr(last_msg, "content") and last_msg.content:
                                yield {
                                    "type": "conclusion",
                                    "content": last_msg.content,
                                }

        except Exception as e:
            logger.exception(f"Deep Path stream failed: {e}")
            yield {
                "type": "error",
                "content": str(e),
            }

    def is_suitable(self, user_query: str) -> bool:
        """
        Check if query is suitable for Deep Path strategy.

        Args:
            user_query: User's query

        Returns:
            True if suitable for Deep Path (diagnostic questions)
        """
        suitable_patterns = [
            "为什么",
            "why",
            "诊断",
            "diagnose",
            "排查",
            "troubleshoot",
            "分析",
            "analyze",
            "investigate",
            "调查",
            "原因",
            "cause",
            "问题",
            "problem",
        ]

        query_lower = user_query.lower()
        return any(pattern in query_lower for pattern in suitable_patterns)
