#!/usr/bin/env python3
"""
Smart query - automatically selects the best command for your intent.

Usage: /smart-query <device> <intent> [--command <specific_command>]

This is the PRIMARY command for device queries. It automatically:
1. Detects device platform from inventory
2. Finds the best matching command for your intent
3. Executes the command and returns results

Examples:
    /smart-query R1 interface
    /smart-query SW1 vlan
    /smart-query R2 bgp
    /smart-query R1 route --command "show ip route ospf"

Common intents: interface, bgp, ospf, route, vlan, mac, arp, version, config
"""
import sys
import argparse
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Load environment
from dotenv import load_dotenv
load_dotenv()


def main():
    """Execute a smart query on a device."""
    parser = argparse.ArgumentParser(
        description="Query a network device with automatic command selection",
        prog="/smart-query"
    )
    parser.add_argument("device", help="Device name (e.g., 'R1', 'SW1')")
    parser.add_argument("intent", help="Query intent (e.g., 'interface', 'bgp', 'ospf')")
    parser.add_argument("--command", "-c", help="Override with specific command")
    
    args = parser.parse_args()
    
    try:
        from olav.tools.smart_query import smart_query
        result = smart_query.invoke({
            "device": args.device,
            "intent": args.intent,
            "command": args.command,
        })
        print(result)
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
