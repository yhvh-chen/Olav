"""Network execution tools for OLAV v0.8.

This module provides tools for executing commands on network devices using Nornir.
Includes command whitelist enforcement, audit logging, and TextFSM structured parsing.

Refactored: Core classes moved to network_executor.py, parsing to network_parser.py
"""

from langchain_core.tools import tool

# Re-export from refactored modules for backward compatibility
from olav.tools.network_executor import (
    CommandExecutionResult,
    NetworkExecutor,
    get_executor,
    get_nornir,
    reset_nornir,
)
from olav.tools.network_parser import estimate_tokens, execute_with_textfsm

# Make exports available at module level
__all__ = [
    "CommandExecutionResult",
    "NetworkExecutor",
    "get_executor",
    "get_nornir",
    "reset_nornir",
    "estimate_tokens",
    "execute_with_textfsm",
    "nornir_execute",
    "list_devices",
    "get_device_platform",
]


@tool
def nornir_execute(device: str, command: str, timeout: int = 30) -> str:
    """Execute a command on a network device using Nornir.

    This tool executes CLI commands on network devices through Nornir/Netmiko.
    Commands must be in the whitelist (defined in agent_dir/imports/commands/*.txt).
    Dangerous commands in the blacklist will be rejected.

    Args:
        device: Device name or IP address from Nornir inventory
        command: CLI command to execute (e.g., "show version", "show interface status")
        timeout: Command timeout in seconds (default: 30)

    Returns:
        Command output or error message

    Examples:
        >>> nornir_execute("R1", "show version")
        "Cisco IOS XE, Version 17.3.1..."

        >>> nornir_execute("core-sw", "show interfaces status")
        "Port  Name  Status  Vlan..."
    """
    executor = get_executor()
    result = executor.execute(device=device, command=command, timeout=timeout)

    if result.success:
        return result.output or ""
    else:
        return f"Error: {result.error}"


@tool
def list_devices(
    role: str | None = None,
    site: str | None = None,
    platform: str | None = None,
    group: str | None = None,
    alias: str | None = None,
) -> str:
    """List devices from the Nornir inventory.

    This tool queries the Nornir inventory to list available network devices.
    Devices can be filtered by role, site, platform, group, or searched by alias.

    Args:
        role: Optional role filter (e.g., "core", "access", "border")
        site: Optional site filter (e.g., "lab", "datacenter")
        platform: Optional platform filter (e.g., "cisco_ios", "huawei_vrp")
        group: Optional group filter (e.g., "test", "core", "border")
        alias: Optional alias search term (e.g., "核心路由器", "边界")
               Searches device name, hostname, role, and aliases field

    Returns:
        List of devices with their properties (including groups)

    Examples:
        >>> list_devices()
        "Available devices:
        - R1 (10.1.1.1) - cisco_ios - border@lab [test]
        - R3 (10.1.1.3) - cisco_ios - core@lab [test]"

        >>> list_devices(group="test")
        "Devices in group 'test':
        - R1, R2, R3, R4, SW1, SW2"

        >>> list_devices(role="core")
        "Core devices:
        - R3 (10.1.1.3) - cisco_ios [test]
        - R4 (10.1.1.4) - cisco_ios [test]"
    """
    try:
        nr = get_nornir()

        # Start with all hosts
        devices = []
        for name, host in nr.inventory.hosts.items():
            hostname = host.hostname or name
            host_platform = host.platform or "unknown"
            host_role = host.get("role", "unknown")
            host_site = host.get("site", "unknown")
            host_aliases = host.get("aliases", []) or []

            # Get groups as list of strings
            if hasattr(host.groups, "keys"):
                host_groups = list(host.groups.keys())
            else:
                host_groups = [str(g) for g in host.groups] if host.groups else []

            # Apply filters
            if role and host_role != role:
                continue
            if site and host_site != site:
                continue
            if platform and host_platform != platform:
                continue
            if group and group not in host_groups:
                continue

            # Alias search - match against name, hostname, role, or aliases
            if alias:
                alias_lower = alias.lower()
                match_found = False
                matched_alias = None

                # Search in device name
                if alias_lower in name.lower():
                    match_found = True
                # Search in hostname
                elif alias_lower in hostname.lower():
                    match_found = True
                # Search in role
                elif alias_lower in host_role.lower():
                    match_found = True
                # Search in aliases list
                else:
                    for a in host_aliases:
                        if alias_lower in a.lower():
                            match_found = True
                            matched_alias = a
                            break

                if not match_found:
                    continue

                # Add matched alias info
                alias_info = f" (alias: {matched_alias})" if matched_alias else ""
                groups_str = f" [{','.join(host_groups)}]" if host_groups else ""
                devices.append(
                    f"- {name} ({hostname}) - {host_platform} - {host_role}@{host_site}{groups_str}{alias_info}"
                )
            else:
                groups_str = f" [{','.join(host_groups)}]" if host_groups else ""
                devices.append(
                    f"- {name} ({hostname}) - {host_platform} - {host_role}@{host_site}{groups_str}"
                )

        if not devices:
            if alias:
                return f"No devices found matching alias '{alias}'."
            if group:
                return f"No devices found in group '{group}'."
            return "No devices found matching the criteria."

        # Generate appropriate header
        if group:
            header = f"Devices in group '{group}':"
        elif role:
            header = f"Devices with role '{role}':"
        elif site:
            header = f"Devices at site '{site}':"
        elif alias:
            header = f"Devices matching '{alias}':"
        else:
            header = "Available devices:"
        return header + "\n" + "\n".join(devices)

    except Exception as e:
        import traceback

        return f"Error listing devices: {e}\n\nTraceback:\n{traceback.format_exc()}"


@tool
def get_device_platform(device: str) -> str:
    """Get the platform type of a specific device.

    This tool retrieves the platform (OS type) for a given device from the Nornir inventory.
    Use this before searching for platform-specific commands.

    Args:
        device: Device name (e.g., "R1", "SW1")

    Returns:
        Platform string (e.g., "cisco_ios", "huawei_vrp") or error message

    Examples:
        >>> get_device_platform("R1")
        "Device R1 platform: cisco_ios"

        >>> get_device_platform("SW1")
        "Device SW1 platform: cisco_ios"
    """
    try:
        nr = get_nornir()
        host = nr.inventory.hosts.get(device)

        if not host:
            return f"Device '{device}' not found in inventory"

        platform = host.platform or "unknown"
        return f"Device {device} platform: {platform}"

    except Exception as e:
        import traceback

        return f"Error getting device platform: {e}\n\nTraceback:\n{traceback.format_exc()}"
