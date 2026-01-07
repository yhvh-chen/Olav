"""Main OLAV agent module for v0.8.

This module creates and configures the OLAV DeepAgent with all necessary tools,
middleware, and system prompts.
"""

from pathlib import Path
from typing import Any

from deepagents import FilesystemMiddleware, create_deep_agent
from langchain_core.tools import BaseTool

from config.settings import settings
from olav.core.llm import LLMFactory
from olav.tools.capabilities import api_call, search_capabilities
from olav.tools.network import list_devices, nornir_execute, get_device_platform
from olav.tools.smart_query import smart_query, batch_query
from olav.tools.loader import reload_capabilities


def create_olav_agent(
    model: str | None = None,
    checkpointer: Any | None = None,
    debug: bool = False,
) -> Any:
    """Create the OLAV DeepAgent.

    This function creates and configures the main OLAV agent with:
    - Network execution tools (nornir_execute, list_devices)
    - Capability search tools (search_capabilities, api_call)
    - Filesystem access (for Skills/Knowledge management)
    - HITL approval for write operations

    Args:
        model: Model name or instance (defaults to configured LLM)
        checkpointer: Optional checkpointer for state persistence
        debug: Enable debug mode

    Returns:
        Compiled DeepAgent ready to use
    """
    # Initialize model from configuration or parameter
    if model is None:
        llm = LLMFactory.get_chat_model()
    elif isinstance(model, str):
        llm = LLMFactory.get_chat_model()  # model_name parameter overridden in init_chat_model
    else:
        llm = model

    # Load system prompt from OLAV.md
    olav_md_path = Path(".olav/OLAV.md")
    if olav_md_path.exists():
        system_prompt = olav_md_path.read_text(encoding="utf-8")
    else:
        # P1: Optimized compact system prompt (~500 tokens vs ~3000)
        system_prompt = """# OLAV - Network AI Assistant

You are OLAV, an AI for network operations. Execute queries efficiently.

## Primary Tools (USE THESE FIRST)
- `smart_query(device, intent)` - Query a device. Auto-selects best command.
  Examples: smart_query("R1", "interface"), smart_query("SW1", "mac")
- `batch_query(devices, intent)` - Query multiple devices. Use "all" for all devices.
  Examples: batch_query("R1,R2", "bgp"), batch_query("all", "version")
- `list_devices()` - Show all available devices

## Secondary Tools (Only if needed)
- `search_capabilities(query, platform)` - Find specific commands
- `nornir_execute(device, command)` - Run a specific command
- `api_call(system, method, endpoint)` - Call external APIs

## Quick Reference
| Intent | Example Query | Auto Command |
|--------|--------------|--------------|
| interface | smart_query("R1", "interface") | show ip interface brief |
| bgp | smart_query("R1", "bgp") | show ip bgp summary |
| ospf | smart_query("R1", "ospf") | show ip ospf neighbor |
| route | smart_query("R1", "route") | show ip route |
| mac | smart_query("SW1", "mac") | show mac address-table |
| vlan | smart_query("SW1", "vlan") | show vlan brief |
| version | smart_query("R1", "version") | show version |

## Rules
- All commands are pre-approved (whitelist). Execute directly.
- Dangerous commands are blocked (blacklist). 
- For file writes, ask for approval.
"""

    # Define tools - smart_query and batch_query are primary (P0 optimization)
    # Secondary tools kept for edge cases
    tools: list[BaseTool] = [
        smart_query,      # P0: Primary tool - combines platform detection + command selection + execution
        batch_query,      # P0: Batch queries across multiple devices
        list_devices,     # Secondary: List available devices
        search_capabilities,  # Secondary: Manual command search
        nornir_execute,   # Secondary: Direct command execution
        api_call,         # Secondary: API calls
    ]

    # Configure HITL - interrupt only on filesystem operations
    # Note: nornir_execute and api_call are safe because they enforce:
    # 1. Whitelist of approved commands (by platform and device type)
    # 2. Blacklist of dangerous patterns (reload, erase, rewrite, etc)
    # All read-only operations proceed automatically. HITL interrupts disabled here.
    interrupt_on = {
        "smart_query": False,   # Safe: uses whitelist internally
        "batch_query": False,   # Safe: uses whitelist internally
        "nornir_execute": False,  # Safe: whitelist + blacklist enforcement
        "api_call": False,  # Safe: API validation in tool layer
        "write_file": True,  # Filesystem operations require approval
        "edit_file": True,  # Filesystem editing requires approval
    }

    # Create agent
    agent = create_deep_agent(
        model=llm,
        tools=tools,
        system_prompt=system_prompt,
        checkpointer=checkpointer,
        interrupt_on=interrupt_on,
        debug=debug,
        name="olav",
    )

    return agent


def initialize_olav() -> Any:
    """Initialize OLAV agent and reload capabilities.

    This is the main entry point for OLAV. It:
    1. Reloads capabilities from imports/ directory
    2. Creates the OLAV agent
    3. Returns the agent for use

    Returns:
        Compiled OLAV DeepAgent
    """
    # Reload capabilities
    print("Loading capabilities from .olav/imports/...")
    counts = reload_capabilities(imports_dir=".olav/imports")
    print(
        f"Loaded {counts['commands']} commands and {counts['apis']} API endpoints "
        f"(total: {counts['total']})"
    )

    # Create and return agent
    return create_olav_agent()


def create_subagent(
    name: str,
    description: str,
    system_prompt: str,
    tools: list[BaseTool] | None = None,
) -> dict[str, Any]:
    """Create a subagent configuration.

    Args:
        name: Subagent name
        description: What this subagent does
        system_prompt: System prompt for the subagent
        tools: Tools available to this subagent

    Returns:
        Subagent configuration dictionary
    """
    return {
        "name": name,
        "description": description,
        "prompt": system_prompt,
        "tools": tools or [],
    }


def get_macro_analyzer() -> dict[str, Any]:
    """Get the macro-analyzer subagent configuration.

    This subagent analyzes network topology, paths, and end-to-end connectivity.

    Returns:
        Subagent configuration
    """
    return create_subagent(
        name="macro-analyzer",
        description="Macro analysis: topology, paths, end-to-end connectivity",
        system_prompt="""You are a network macro-analysis expert.

Your responsibilities:
1. Analyze network topology (LLDP/CDP/BGP neighbors)
2. Trace data paths (traceroute, routing tables)
3. Check end-to-end connectivity
4. Identify failure domains (which area/device has issues)

Working method: Start from a global view, progressively narrow down the scope.

Available tools:
- nornir_execute: Execute commands on network devices
- list_devices: List available devices
- search_capabilities: Find available commands
""",
        tools=[nornir_execute, list_devices, search_capabilities],
    )


def get_micro_analyzer() -> dict[str, Any]:
    """Get the micro-analyzer subagent configuration.

    This subagent performs TCP/IP layer-by-layer troubleshooting.

    Returns:
        Subagent configuration
    """
    return create_subagent(
        name="micro-analyzer",
        description="Micro analysis: TCP/IP layer-by-layer troubleshooting",
        system_prompt="""You are a network micro-analysis expert, troubleshooting by TCP/IP layers.

Troubleshooting order (bottom-up):
1. **Physical Layer**: Port status, optical power, CRC errors
2. **Data Link Layer**: VLAN, MAC table, STP state
3. **Network Layer**: IP addresses, routing table, ARP
4. **Transport Layer**: ACLs, NAT, port filtering
5. **Application Layer**: DNS, service reachability

Working method: Start from the physical layer, work upward layer by layer.

Available tools:
- nornir_execute: Execute commands on network devices
- search_capabilities: Find available commands
""",
        tools=[nornir_execute, search_capabilities],
    )
