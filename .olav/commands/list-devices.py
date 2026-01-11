#!/usr/bin/env python3
"""
List available network devices from inventory.

Usage: /list-devices [--role <role>] [--site <site>] [--platform <platform>]

Examples:
    /list-devices
    /list-devices --role core
    /list-devices --platform cisco_ios
    /list-devices --site datacenter1

Options:
    --role       Filter by device role (core, access, distribution)
    --site       Filter by site name
    --platform   Filter by platform (cisco_ios, huawei_vrp)
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


def main():
    """List available devices from inventory."""
    parser = argparse.ArgumentParser(
        description="List network devices from inventory",
        prog="/list-devices"
    )
    parser.add_argument("--role", "-r", help="Filter by role")
    parser.add_argument("--site", "-s", help="Filter by site")
    parser.add_argument("--platform", "-p", help="Filter by platform")

    args = parser.parse_args()

    try:
        from olav.tools.network import list_devices
        result = list_devices.invoke({
            "role": args.role,
            "site": args.site,
            "platform": args.platform,
        })
        print(result)
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
