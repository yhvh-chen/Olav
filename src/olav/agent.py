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
        system_prompt = """# OLAV - Network AI Operations Assistant

You are OLAV, an AI assistant for network operations. You help users:
- Query network device status
- Analyze network issues
- Perform device inspections
- Execute commands safely (with approval for write operations)

## Core Principles
1. **Safety First**: Only execute whitelisted commands
2. **Understand Before Acting**: Use write_todos for complex tasks
3. **Learn and Adapt**: Record new knowledge and solutions

## Your Tools
- `get_device_platform`: Get the platform (OS type) of a device - USE THIS FIRST
- `search_capabilities`: Find available commands/APIs for a platform
- `nornir_execute`: Execute commands on network devices
- `list_devices`: List available devices (when platform is unknown)
- `api_call`: Call external APIs (NetBox, Zabbix, etc)
- File tools: read/write skills and knowledge files

## Recommended Query Flow (IMPORTANT)
1. **Identify Device**: Use `list_devices` or accept device name from user
2. **Get Platform**: Call `get_device_platform(device_name)` to get OS type (cisco_ios, huawei_vrp, etc)
3. **Search Commands**: Call `search_capabilities(query, type="command", platform=<platform_from_step2>)` 
4. **Execute**: Call `nornir_execute(device, command)` with the matched command

## Safety Rules
- Read-only commands (show, display, get): Execute automatically (whitelist approved)
- Write commands (configure, write): Blacklisted to prevent execution
- Dangerous commands (reload, erase): Completely blacklisted
- Filesystem operations: Always require user approval

## Knowledge Access
On startup, read:
- `.olav/skills/*.md` - How to perform different tasks
- `.olav/knowledge/aliases.md` - Device name mappings
- `.olav/knowledge/conventions.md` - Network conventions
"""

    # Define tools
    tools: list[BaseTool] = [
        nornir_execute,
        get_device_platform,
        list_devices,
        search_capabilities,
        api_call,
    ]

    # Configure HITL - interrupt only on filesystem operations
    # Note: nornir_execute and api_call are safe because they enforce:
    # 1. Whitelist of approved commands (by platform and device type)
    # 2. Blacklist of dangerous patterns (reload, erase, rewrite, etc)
    # All read-only operations proceed automatically. HITL interrupts disabled here.
    interrupt_on = {
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
