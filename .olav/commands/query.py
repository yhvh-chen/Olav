#!/usr/bin/env python3
"""Execute quick network query.

Usage: /query [device] [query]
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Load environment
from dotenv import load_dotenv

load_dotenv()


# Query patterns to command mapping
QUERY_PATTERNS = {
    # Interface queries
    "interface status": "show interfaces status",
    "interface brief": "show ip interface brief",
    "interface errors": "show interfaces counters errors",
    "interface": "show interfaces {arg}",
    # Routing queries
    "route": "show ip route",
    "route summary": "show ip route summary",
    "routing": "show ip route",
    "bgp": "show ip bgp summary",
    "bgp neighbor": "show ip bgp neighbors",
    "ospf": "show ip ospf neighbor",
    "ospf neighbor": "show ip ospf neighbor",
    # System queries
    "version": "show version",
    "uptime": "show version | include uptime",
    "cpu": "show processes cpu sorted | head 10",
    "memory": "show memory statistics",
    "inventory": "show inventory",
    # Layer 2 queries
    "vlan": "show vlan brief",
    "mac": "show mac address-table",
    "mac address": "show mac address-table",
    "arp": "show arp",
    "cdp": "show cdp neighbors",
    "lldp": "show lldp neighbors",
    "spanning": "show spanning-tree summary",
    "stp": "show spanning-tree summary",
    # Config queries
    "config": "show running-config",
    "running": "show running-config",
    "startup": "show startup-config",
    "acl": "show access-lists",
    # Status queries
    "status": "show interfaces status",
    "neighbors": "show cdp neighbors",
    "log": "show logging | tail 20",
    "clock": "show clock",
}


def find_matching_command(query: str) -> str:
    """Find the best matching command for a query."""
    query_lower = query.lower()

    # Exact match first
    if query_lower in QUERY_PATTERNS:
        return QUERY_PATTERNS[query_lower]

    # Partial match
    for pattern, command in QUERY_PATTERNS.items():
        if pattern in query_lower or query_lower in pattern:
            return command

    # Word match
    query_words = set(query_lower.split())
    best_match = None
    best_score = 0

    for pattern, command in QUERY_PATTERNS.items():
        pattern_words = set(pattern.split())
        overlap = len(query_words & pattern_words)
        if overlap > best_score:
            best_score = overlap
            best_match = command

    if best_match:
        return best_match

    # Default: treat query as raw command
    return query


def resolve_device_alias(alias: str) -> str:
    """Resolve device alias to actual device name.

    Checks knowledge/aliases.md for mappings.
    """
    try:
        from config.settings import settings

        alias_file = Path(settings.agent_dir) / "knowledge" / "aliases.md"

        if alias_file.exists():
            content = alias_file.read_text()
            for line in content.split("\n"):
                if ":" in line or "→" in line:
                    # Parse: "core-sw: S1" or "core-sw → S1"
                    parts = line.replace("→", ":").split(":")
                    if len(parts) >= 2:
                        key = parts[0].strip().lower()
                        value = parts[1].strip()
                        if key == alias.lower():
                            return value
    except Exception as e:  # noqa: S110, F841
        pass

    return alias


def execute_query(device: str, query: str) -> str:
    """Execute query on device and return formatted result."""
    # Resolve alias
    actual_device = resolve_device_alias(device)

    # Find matching command
    command = find_matching_command(query)

    # Handle command with argument placeholder
    if "{arg}" in command:
        # Extract argument from query
        words = query.split()
        if len(words) > 1:
            arg = words[-1]  # Last word as argument
            command = command.replace("{arg}", arg)
        else:
            command = command.replace("{arg}", "")

    print(f"📡 Device: {actual_device}")
    print(f"💻 Command: {command}")
    print("")

    try:
        from olav.tools.network import nornir_execute

        result = nornir_execute.invoke({"device": actual_device, "command": command})

        if "Error:" in result:
            return f"❌ {result}"

        return f"```\n{result}\n```"

    except Exception as e:
        return f"❌ Error: {e}"


def main():
    """Execute query workflow."""
    parser = argparse.ArgumentParser(description="Execute quick network query", prog="/query")
    parser.add_argument("device", help="Device name or alias")
    parser.add_argument("query", nargs="*", help="Query (e.g., 'interface status', 'bgp')")

    args = parser.parse_args()

    if not args.query:
        print("Error: query required", file=sys.stderr)
        print("Usage: /query <device> <query>", file=sys.stderr)
        print("\nExamples:")
        print("  /query R1 interface status")
        print("  /query S1 version")
        print("  /query R1 bgp neighbors")
        print("  /query all cpu")
        return 1

    query_str = " ".join(args.query)

    # Handle "all" device
    if args.device.lower() == "all":
        try:
            from olav.tools.network import list_devices

            result = list_devices.invoke({})
            devices = _extract_device_names(result)

            print(f"🔍 Querying {len(devices)} devices: {query_str}\n")

            for device in devices:
                print(f"\n{'=' * 40}")
                print(f"Device: {device}")
                print("=" * 40)
                output = execute_query(device, query_str)
                print(output)

            return 0
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
    else:
        output = execute_query(args.device, query_str)
        print(output)
        return 0


def _extract_device_names(list_output: str) -> list:
    """Extract device names from list_devices output."""
    devices = []
    for line in list_output.split("\n"):
        if line.startswith("- "):
            parts = line.split()
            if len(parts) >= 2:
                devices.append(parts[1])
    return devices


if __name__ == "__main__":
    sys.exit(main())
