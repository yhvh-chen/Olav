"""Smart query tool for OLAV v0.8 - Optimized single-call device queries.

This module implements P0 optimization: combining multiple tool calls into one
to reduce LLM decision cycles from 4-5 down to 1-2.

Also implements P2: Command mapping cache to avoid repeated database lookups.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from langchain_core.tools import tool
from nornir import InitNornir

from config.settings import settings
from olav.core.database import get_database


# ============================================================================
# P2: Command Mapping Cache
# ============================================================================

@lru_cache(maxsize=50)
def get_cached_commands(platform: str, intent: str) -> list[str]:
    """Cache command lookups by platform and intent.
    
    Args:
        platform: Device platform (e.g., "cisco_ios", "huawei_vrp")
        intent: Query intent keyword (e.g., "interface", "bgp", "ospf")
    
    Returns:
        List of matching command names
    """
    db = get_database()
    results = db.search_capabilities(
        query=intent,
        cap_type="command",
        platform=platform,
        limit=10,
    )
    return [r["name"] for r in results if not r["is_write"]]


def get_best_command(platform: str, intent: str) -> str | None:
    """Get the best matching command for an intent.
    
    Priority:
    1. Exact match with "brief" (more concise output)
    2. Exact keyword match
    3. First available command
    
    Args:
        platform: Device platform
        intent: Query intent keyword
    
    Returns:
        Best matching command or None
    """
    commands = get_cached_commands(platform, intent)
    
    if not commands:
        return None
    
    # Prefer "brief" commands for concise output
    for cmd in commands:
        if "brief" in cmd.lower():
            return cmd
    
    # Prefer commands that start with "show" for Cisco
    for cmd in commands:
        if cmd.lower().startswith("show "):
            return cmd
    
    # Prefer commands that start with "display" for Huawei
    for cmd in commands:
        if cmd.lower().startswith("display "):
            return cmd
    
    # Return first available
    return commands[0] if commands else None


# ============================================================================
# Device Info Cache (in-memory for session)
# ============================================================================

_device_cache: dict[str, dict] = {}


def get_device_info(device_name: str) -> dict | None:
    """Get device information from Nornir inventory with caching.
    
    Args:
        device_name: Device name (e.g., "R1", "SW1")
    
    Returns:
        Dict with hostname, platform, role, site or None if not found
    """
    if device_name in _device_cache:
        return _device_cache[device_name]
    
    try:
        config_path = Path(".olav/config/nornir/config.yaml").resolve()
        nr = InitNornir(config_file=str(config_path))
        
        host = nr.inventory.hosts.get(device_name)
        if not host:
            return None
        
        info = {
            "name": device_name,
            "hostname": host.hostname or device_name,
            "platform": host.platform or "unknown",
            "role": host.get("role", "unknown"),
            "site": host.get("site", "unknown"),
        }
        
        _device_cache[device_name] = info
        return info
        
    except Exception:
        return None


# ============================================================================
# P0: Smart Query Tool (Combines platform detection + command search + execution)
# ============================================================================

@tool
def smart_query(
    device: str,
    intent: str,
    command: str | None = None,
) -> str:
    """Query a network device with automatic command selection.

    This is the PRIMARY tool for device queries. It automatically:
    1. Detects device platform from inventory
    2. Finds the best matching command for your intent
    3. Executes the command and returns results

    Use this instead of calling get_device_platform + search_capabilities + nornir_execute separately.

    Args:
        device: Device name (e.g., "R1", "SW1", "core-router")
        intent: What you want to query (e.g., "interface", "bgp", "ospf", "route", "mac")
        command: Optional specific command to run (overrides auto-selection)

    Returns:
        Command output with device info, or error message

    Examples:
        >>> smart_query("R1", "interface")
        "## R1 (cisco_ios) - Interface Status
        [show ip interface brief output]"

        >>> smart_query("SW1", "mac")
        "## SW1 (cisco_ios) - MAC Address Table
        [show mac address-table output]"

        >>> smart_query("R2", "bgp")
        "## R2 (cisco_ios) - BGP Status
        [show ip bgp summary output]"
    """
    # Step 1: Get device info
    info = get_device_info(device)
    if not info:
        return f"Error: Device '{device}' not found in inventory. Use list_devices to see available devices."
    
    platform = info["platform"]
    hostname = info["hostname"]
    
    # Step 2: Determine command
    if command:
        selected_command = command
    else:
        selected_command = get_best_command(platform, intent)
        if not selected_command:
            # Try broader search
            cached = get_cached_commands(platform, intent)
            if cached:
                selected_command = cached[0]
            else:
                return (
                    f"Error: No commands found for intent '{intent}' on platform '{platform}'.\n"
                    f"Available intents: interface, bgp, ospf, route, vlan, mac, arp, version, config"
                )
    
    # Step 3: Execute command
    from olav.tools.network import get_executor
    
    executor = get_executor()
    result = executor.execute(device=device, command=selected_command)
    
    # Step 4: Format output
    if result.success:
        return (
            f"## {device} ({platform}) - {intent.title()} Query\n"
            f"**Device**: {hostname} | **Role**: {info['role']} | **Site**: {info['site']}\n"
            f"**Command**: `{selected_command}`\n\n"
            f"```\n{result.output}\n```"
        )
    else:
        return (
            f"## {device} ({platform}) - Query Failed\n"
            f"**Command**: `{selected_command}`\n"
            f"**Error**: {result.error}"
        )


@tool  
def batch_query(
    devices: str,
    intent: str,
) -> str:
    """Query multiple devices with the same intent.

    Executes the same type of query across multiple devices in parallel.
    Much faster than querying devices one by one.

    Args:
        devices: Comma-separated device names (e.g., "R1,R2,R3" or "all")
        intent: What you want to query (e.g., "interface", "bgp", "version")

    Returns:
        Combined output from all devices

    Examples:
        >>> batch_query("R1,R2,R3", "bgp")
        "## Batch Query: bgp
        ### R1: [output]
        ### R2: [output]  
        ### R3: [output]"

        >>> batch_query("all", "version")
        "## Batch Query: version (6 devices)
        [output from all devices]"
    """
    from olav.tools.network import list_devices as _list_devices
    
    # Parse device list
    if devices.lower() == "all":
        # Get all devices from inventory
        try:
            config_path = Path(".olav/config/nornir/config.yaml").resolve()
            nr = InitNornir(config_file=str(config_path))
            device_list = list(nr.inventory.hosts.keys())
        except Exception as e:
            return f"Error loading inventory: {e}"
    else:
        device_list = [d.strip() for d in devices.split(",")]
    
    if not device_list:
        return "Error: No devices specified"
    
    # Query each device
    results = []
    for device in device_list:
        # Use smart_query internally
        info = get_device_info(device)
        if not info:
            results.append(f"### {device}\n❌ Not found in inventory\n")
            continue
        
        platform = info["platform"]
        selected_command = get_best_command(platform, intent)
        
        if not selected_command:
            results.append(f"### {device}\n❌ No command for intent '{intent}'\n")
            continue
        
        from olav.tools.network import get_executor
        executor = get_executor()
        result = executor.execute(device=device, command=selected_command)
        
        if result.success:
            # Truncate long output for batch
            output = result.output or ""
            if len(output) > 500:
                output = output[:500] + "\n... (truncated)"
            results.append(f"### {device} ({platform})\n```\n{output}\n```\n")
        else:
            results.append(f"### {device}\n❌ Error: {result.error}\n")
    
    return f"## Batch Query: {intent} ({len(device_list)} devices)\n\n" + "\n".join(results)


# ============================================================================
# Cache Management
# ============================================================================

def clear_command_cache() -> None:
    """Clear the command mapping cache."""
    get_cached_commands.cache_clear()


def clear_device_cache() -> None:
    """Clear the device info cache."""
    global _device_cache
    _device_cache = {}


def get_cache_stats() -> dict:
    """Get cache statistics."""
    return {
        "command_cache": get_cached_commands.cache_info()._asdict(),
        "device_cache_size": len(_device_cache),
    }
