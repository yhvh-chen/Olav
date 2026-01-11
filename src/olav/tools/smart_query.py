"""Smart query tool for OLAV v0.8 - Optimized single-call device queries.

This module implements P0 optimization: combining multiple tool calls into one
to reduce LLM decision cycles from 4-5 down to 1-2.

Also implements P2: Command mapping cache to avoid repeated database lookups.
Also implements P4: Nornir connection pool singleton.
Also implements P5: Batch query parallelization using Nornir native parallel execution.
"""

from functools import lru_cache

from langchain_core.tools import tool

from olav.core.database import get_database
from olav.tools.network import get_nornir

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
        # P4: Use singleton Nornir instance
        nr = get_nornir()

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
    """Query network devices with automatic command selection.

    This is the PRIMARY tool for device queries. It automatically:
    1. Detects device platform from inventory
    2. Finds the best matching command for your intent
    3. Executes the command and returns results

    Supports both single and multiple devices:
    - Single: "R1"
    - Multiple: "R1,R2,R3"
    - All: "all"
    - Filter: "role:core", "site:lab", "group:test"

    Args:
        device: Device name(s) or filter expression:
                - Single device: "R1"
                - Multiple devices: "R1,R2,R3"
                - All devices: "all"
                - By role: "role:core", "role:border"
                - By site: "site:lab"
                - By group: "group:test"
        intent: What you want to query (e.g., "interface", "bgp", "ospf", "route", "mac")
        command: Optional specific command to run (overrides auto-selection)

    Returns:
        Command output with device info, or error message

    Examples:
        >>> smart_query("R1", "interface")
        "## R1 (cisco_ios) - Interface Status
        [show ip interface brief output]"

        >>> smart_query("R1,R2", "bgp")
        "## Batch Query: bgp (2 devices)
        [output from both devices]"

        >>> smart_query("role:core", "version")
        "## Batch Query: version (2 devices - role:core)
        [output from R3, R4]"

        >>> smart_query("all", "version")
        "## Batch Query: version (6 devices)
        [output from all devices]"
    """
    # Check if this is a batch query (multiple devices)
    is_batch = (
        "," in device or device.lower() == "all" or ":" in device  # role:, site:, group: filters
    )

    if is_batch:
        return _batch_query_internal(device, intent, command)

    # Single device query
    # Step 1: Get device info
    info = get_device_info(device)
    if not info:
        return (
            f"Error: Device '{device}' not found in inventory. "
            f"Use list_devices to see available devices."
        )

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
                    f"Error: No commands found for intent '{intent}' on platform "
                    f"'{platform}'.\nAvailable intents: interface, bgp, ospf, route, "
                    f"vlan, mac, arp, version, config"
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


def _batch_query_internal(
    devices: str,
    intent: str,
    command: str | None = None,
) -> str:
    """Internal batch query implementation.

    Handles: "R1,R2", "all", "role:core", "site:lab", "group:test"
    """
    from nornir_netmiko.tasks import netmiko_send_command

    # Get singleton Nornir instance
    nr = get_nornir()

    filter_desc = ""

    # Parse device specification
    if devices.lower() == "all":
        device_list = list(nr.inventory.hosts.keys())
        filter_desc = "all"
    elif devices.startswith("role:"):
        # Filter by role
        role = devices.split(":", 1)[1].strip()
        device_list = [
            name for name, host in nr.inventory.hosts.items() if host.get("role") == role
        ]
        filter_desc = f"role:{role}"
    elif devices.startswith("site:"):
        # Filter by site
        site = devices.split(":", 1)[1].strip()
        device_list = [
            name for name, host in nr.inventory.hosts.items() if host.get("site") == site
        ]
        filter_desc = f"site:{site}"
    elif devices.startswith("group:"):
        # Filter by group
        group = devices.split(":", 1)[1].strip()
        device_list = []
        for name, host in nr.inventory.hosts.items():
            if hasattr(host.groups, "keys"):
                if group in host.groups.keys():
                    device_list.append(name)
            elif isinstance(host.groups, (list, tuple)):
                if group in [str(g) for g in host.groups]:
                    device_list.append(name)
        filter_desc = f"group:{group}"
    else:
        # Comma-separated device names
        device_list = [d.strip() for d in devices.split(",")]

    if not device_list:
        return f"Error: No devices found matching '{devices}'"

    # Validate devices exist
    valid_devices = []
    invalid_devices = []
    for device in device_list:
        if device in nr.inventory.hosts:
            valid_devices.append(device)
        else:
            invalid_devices.append(device)

    if not valid_devices:
        return f"Error: No valid devices found. Invalid: {', '.join(invalid_devices)}"

    # Determine command per platform (group devices by platform)
    # Most common case: all same platform, use same command
    platform_commands: dict[str, str] = {}
    device_commands: dict[str, str] = {}

    for device in valid_devices:
        info = get_device_info(device)
        if not info:
            continue
        platform = info["platform"]

        if platform not in platform_commands:
            cmd = get_best_command(platform, intent)
            platform_commands[platform] = cmd

        device_commands[device] = platform_commands[platform]

    # Check if we have a command for all devices
    devices_without_cmd = [d for d in valid_devices if not device_commands.get(d)]
    if devices_without_cmd:
        return (
            f"Error: No command for intent '{intent}' on devices: {', '.join(devices_without_cmd)}"
        )

    # P5: Use Nornir parallel execution
    # Group devices by command to minimize task variations
    command_devices: dict[str, list[str]] = {}
    for device, cmd in device_commands.items():
        if cmd not in command_devices:
            command_devices[cmd] = []
        command_devices[cmd].append(device)

    # Execute in parallel per command group
    all_results: dict[str, dict] = {}

    for command, cmd_devices_list in command_devices.items():
        # Filter Nornir to these devices
        # Use default argument to capture loop variable
        nr_filtered = nr.filter(filter_func=lambda h, devices=cmd_devices_list: h.name in devices)

        # Execute command in parallel (Nornir handles threading)
        agg_result = nr_filtered.run(
            task=netmiko_send_command,
            command_string=command,
            read_timeout=30,
        )

        # Collect results
        for device_name, result in agg_result.items():
            if result.failed:
                error_msg = str(result.exception) if result.exception else "Unknown error"
                all_results[device_name] = {
                    "success": False,
                    "error": error_msg,
                    "command": command,
                }
            else:
                all_results[device_name] = {
                    "success": True,
                    "output": str(result.result),
                    "command": command,
                }

    # Format output
    results_formatted = []
    for device in valid_devices:
        info = get_device_info(device)
        platform = info["platform"] if info else "unknown"

        if device in all_results:
            result = all_results[device]
            if result["success"]:
                output = result["output"]
                # Truncate long output for batch display
                if len(output) > 500:
                    output = output[:500] + "\n... (truncated)"
                results_formatted.append(f"### {device} ({platform})\n```\n{output}\n```\n")
            else:
                results_formatted.append(f"### {device}\n❌ Error: {result['error']}\n")
        else:
            results_formatted.append(f"### {device}\n❌ Not processed\n")

    # Add invalid devices to output
    for device in invalid_devices:
        results_formatted.append(f"### {device}\n❌ Not found in inventory\n")

    header = f"## Batch Query: {intent} ({len(valid_devices)} devices"
    if filter_desc:
        header += f" - {filter_desc}"
    if invalid_devices:
        header += f", {len(invalid_devices)} not found"
    header += ")\n\n"

    return header + "\n".join(results_formatted)


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
