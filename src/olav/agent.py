"""Main OLAV agent module for v0.8.

This module creates and configures the OLAV DeepAgent with all necessary tools,
middleware, and system prompts.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any

from deepagents import create_deep_agent
from langchain_core.tools import BaseTool

from config.settings import settings
from olav.core.llm import LLMFactory
from olav.core.skill_loader import get_skill_loader
from olav.core.storage import get_storage_permissions
from olav.core.subagent_manager import format_subagent_descriptions, get_subagent_middleware
from olav.tools.capabilities import api_call, search_capabilities
from olav.tools.inspection_tools import (
    generate_report,
    nornir_bulk_execute,
    parse_inspection_scope,
)
from olav.tools.learning_tools import (
    save_solution_tool,
    suggest_filename_tool,
)
from olav.tools.loader import reload_capabilities
from olav.tools.network import list_devices, nornir_execute
from olav.tools.smart_query import batch_query, smart_query

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph


def create_olav_agent(
    model: str | None = None,
    checkpointer: object | None = None,
    debug: bool = False,
    enable_skill_routing: bool = True,
    enable_subagents: bool = True,
    enable_hitl: bool | None = None,
) -> "CompiledStateGraph":
    """Create the OLAV DeepAgent.

    This function creates and configures the main OLAV agent with:
    - Network execution tools (nornir_execute, list_devices)
    - Capability search tools (search_capabilities, api_call)
    - Filesystem access (for Skills/Knowledge management)
    - HITL approval for write operations
    - Skill routing (optional, default enabled)
    - Subagent delegation (optional, default enabled for Phase 3)

    Args:
        model: Model name or instance (defaults to configured LLM)
        checkpointer: Optional checkpointer for state persistence
        debug: Enable debug mode
        enable_skill_routing: Enable skill-based routing (default True)
        enable_subagents: Enable subagent delegation (default True)
        enable_hitl: Enable HITL approval for write operations.
                     If None, uses settings.enable_hitl (default True).
                     Set to False for automated testing.

    Returns:
        Compiled DeepAgent ready to use
    """
    # Use settings default if not explicitly provided
    if enable_hitl is None:
        enable_hitl = settings.enable_hitl
    # Initialize model from configuration or parameter
    if model is None:
        llm = LLMFactory.get_chat_model()
    elif isinstance(model, str):
        llm = LLMFactory.get_chat_model()  # model_name parameter overridden in init_chat_model
    else:
        llm = model

    # Load base system prompt from OLAV.md or use default
    olav_md_path = Path(".olav/OLAV.md")
    if olav_md_path.exists():
        base_prompt = olav_md_path.read_text(encoding="utf-8")
    else:
        # P1: Optimized compact system prompt (~500 tokens vs ~3000)
        base_prompt = """# OLAV - Network AI Assistant

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

    # Inject skill guidance if enabled
    if enable_skill_routing:
        skill_loader = get_skill_loader()
        skills = skill_loader.load_all()
        if skills:
            skill_summary = _format_skills_for_prompt(skills)
            system_prompt = f"{base_prompt}\n\n## Skill Guidance\n{skill_summary}"
        else:
            system_prompt = base_prompt
    else:
        system_prompt = base_prompt

    # Inject subagent descriptions if enabled (Phase 3)
    if enable_subagents:
        subagent_desc = format_subagent_descriptions()
        system_prompt = f"{system_prompt}\n\n{subagent_desc}"

    # Inject storage permissions (Phase 4)
    # Note: Removed learning_guidance to reduce LLM exploration behavior
    # Learning tools are still available but not actively guided
    storage_permissions = get_storage_permissions()
    system_prompt = f"{system_prompt}\n\n{storage_permissions}"

    # Define tools - smart_query and batch_query are primary (P0 optimization)
    # Secondary tools kept for edge cases
    tools: list[BaseTool] = [
        # P0: Primary tool - combines platform detection + command selection + execution
        smart_query,
        batch_query,  # P0: Batch queries across multiple devices
        list_devices,  # Secondary: List available devices
        search_capabilities,  # Secondary: Manual command search
        nornir_execute,  # Secondary: Direct command execution
        api_call,  # Secondary: API calls
        # Phase 4: Learning tools - self-learning capabilities
        save_solution_tool,  # Save successful troubleshooting cases
        suggest_filename_tool,  # Suggest solution filenames
        # Note: update_aliases_tool removed - aliases managed via Nornir hosts.yaml
    ]

    # Configure HITL - interrupt only on filesystem operations
    # Note: nornir_execute and api_call are safe because they enforce:
    # 1. Whitelist of approved commands (by platform and device type)
    # 2. Blacklist of dangerous patterns (reload, erase, rewrite, etc)
    # All read-only operations proceed automatically. HITL interrupts disabled here.
    if enable_hitl:
        interrupt_on = {
            "smart_query": False,  # Safe: uses whitelist internally
            "batch_query": False,  # Safe: uses whitelist internally
            "nornir_execute": False,  # Safe: whitelist + blacklist enforcement
            "api_call": False,  # Safe: API validation in tool layer
            "save_solution": True,  # Phase 4: Learning - requires approval (writes to disk)
            "update_aliases": True,  # Phase 4: Learning - requires approval (writes to disk)
            "suggest_solution_filename": False,  # Phase 4: Learning - read-only helper
            "write_file": True,  # Filesystem operations require approval
            "edit_file": True,  # Filesystem editing requires approval
        }
    else:
        # HITL disabled - all operations proceed without approval (for testing)
        interrupt_on = None

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

    # Add subagent middleware if enabled (Phase 3)
    if enable_subagents:
        # Note: SubAgentMiddleware creates general-purpose subagents (DeepAgents limitation)
        # but each is configured with a specialized system prompt to enable
        # macro-analyzer and micro-analyzer functionality
        _ = get_subagent_middleware(tools=tools, default_model=llm)

    return agent


def initialize_olav() -> "CompiledStateGraph":
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
        "system_prompt": system_prompt,  # DeepAgents expects 'system_prompt' not 'prompt'
        "tools": tools or [],
    }


# Subagent configuration functions are now in this module
# Kept for backward compatibility with external code
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


def get_inspector_agent() -> dict[str, Any]:
    """Get the inspector-agent subagent configuration (Phase 5).

    This subagent specializes in device inspection workflows:
    - Health checks
    - BGP audits
    - Interface error analysis
    - Security baseline checks

    Returns:
        Subagent configuration
    """
    return create_subagent(
        name="inspector-agent",
        description="Device inspection specialist: health checks, audits, security analysis",
        system_prompt="""You are the Network Inspector Agent, specialized in device inspection workflows.

Your expertise includes:
1. **Health Checks**: System resources, CPU, memory, uptime
2. **BGP Audits**: BGP peer status, route tables, AS paths
3. **Interface Analysis**: Error counters, utilization, CRC errors
4. **Security Baseline**: ACL checks, password complexity, NTP/SNMP config

## Inspection Workflow

When given an inspection task:

1. **Parse Scope**: Identify which devices to inspect
   - Use `parse_inspection_scope()` to parse device filters
   - Examples: "all core routers", "R1-R5", "devices with tag:production"

2. **Plan Commands**: Based on inspection type, select commands
   - Health check: show version, show processes cpu, show memory statistics
   - BGP audit: show ip bgp summary, show ip bgp neighbors
   - Interface errors: show interfaces counters errors
   - Security: show access-lists, show running-config | section ntp

3. **Bulk Execute**: Use `nornir_bulk_execute()` for efficiency
   - Pass all devices and commands at once
   - Returns structured results per device

4. **Analyze Results**: Identify issues and patterns
   - Look for errors, warnings, anomalies
   - Compare against baselines

5. **Generate Report**: Use `generate_report()` for structured output
   - HTML format for detailed analysis
   - Actionable recommendations

Available tools:
- nornir_bulk_execute: Execute commands on multiple devices in parallel
- parse_inspection_scope: Parse device filter expressions
- generate_report: Generate HTML inspection reports
- nornir_execute: Execute commands on individual devices
- search_capabilities: Find available inspection commands
""",
        tools=[
            nornir_bulk_execute,
            parse_inspection_scope,
            generate_report,
            nornir_execute,
            search_capabilities,
        ],
    )


def _format_skills_for_prompt(skills: dict[str, Any]) -> str:
    """Format skills for inclusion in system prompt.

    Args:
        skills: Dictionary of Skill objects

    Returns:
        Formatted skill descriptions for prompt
    """
    skill_lines = []
    for skill_id, skill in skills.items():
        skill_lines.append(f"- **{skill_id}** ({skill.complexity}): {skill.description}")

    return "When approaching tasks, consider these execution strategies:\n" + "\n".join(skill_lines)
