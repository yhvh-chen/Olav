"""Subagent Configurations - Defines specialized network analysis subagents.

This module contains the configuration definitions for subagents used by OLAV.
Moved from agent.py to avoid circular imports with subagent_manager.py.
"""

from typing import Any


def create_subagent(
    name: str,
    description: str,
    system_prompt: str,
    tools: list[Any] | None = None,
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


def get_macro_analyzer(tools: list[Any] | None = None) -> dict[str, Any]:
    """Get the macro-analyzer subagent configuration.

    This subagent analyzes network topology, paths, and end-to-end connectivity.

    Args:
        tools: Optional list of tools to provide (injected at runtime)

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
- smart_query: Intelligent device query
- batch_query: Query multiple devices at once
""",
        tools=tools,
    )


def get_micro_analyzer(tools: list[Any] | None = None) -> dict[str, Any]:
    """Get the micro-analyzer subagent configuration.

    This subagent performs TCP/IP layer-by-layer troubleshooting.

    Args:
        tools: Optional list of tools to provide (injected at runtime)

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
- smart_query: Intelligent device query
""",
        tools=tools,
    )


def get_inspector_agent(tools: list[Any] | None = None) -> dict[str, Any]:
    """Get the inspector-agent subagent configuration (Phase 5).

    This subagent specializes in device inspection workflows:
    - Health checks
    - BGP audits
    - Interface error analysis
    - Security baseline checks

    Args:
        tools: Optional list of tools to provide (injected at runtime)

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
   - Highlight critical issues

5. **Generate Report**: Use `generate_report()` with Jinja2 template
   - Select appropriate template (health-check, bgp-audit, etc.)
   - Include findings, recommendations, and metrics

## Scope Parsing Examples

- "all core routers" → Filter by role:core
- "R1, R2, R5" → Specific device names
- "devices in site:DC1" → Filter by site attribute
- "all" → No filter, inspect all devices

## Important Notes

- Always use `nornir_bulk_execute()` for multiple devices (efficient)
- Use `parse_inspection_scope()` before executing commands
- Always generate a report using Jinja2 templates
- Reports are saved to `.olav/reports/` directory
- Include actionable recommendations in your reports

## Tool Usage

```python
# Parse inspection scope
devices = parse_inspection_scope("all core routers")

# Bulk execute commands
results = nornir_bulk_execute(
    devices=devices,
    commands=["show version", "show processes cpu"],
    max_workers=10  # Parallel execution
)

# Generate report
report_path = generate_report(
    template="health-check",
    results=results,
    output_path=".olav/reports/health-check-20250108.html"
)
```

Be thorough, accurate, and provide clear actionable recommendations in your reports.

Available tools:
- nornir_bulk_execute: Execute commands on multiple devices in parallel
- parse_inspection_scope: Parse device filter expressions
- generate_report: Generate HTML reports using Jinja2 templates
- list_devices: List available devices
- search_capabilities: Find available commands
""",
        tools=tools,
    )
