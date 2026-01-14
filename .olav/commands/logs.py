#!/usr/bin/env python3
"""Logs command - Query network events.

Usage: /logs [device] [filters...]
"""

import argparse
import sys
from pathlib import Path

# Add project root to path for olav imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Load environment
from dotenv import load_dotenv

load_dotenv()


def main():
    """Execute logs query."""
    parser = argparse.ArgumentParser(description="Query network events", prog="/logs")
    parser.add_argument("--device", help="Filter by device")
    parser.add_argument("--type", help="Filter by event type (UPDOWN, ADJCHG, etc.)")
    parser.add_argument("--severity", type=int, default=5, help="Maximum severity (default: 5)")
    parser.add_argument("--time-range", default="24h", help="Time range (24h, 7d, 30d)")
    parser.add_argument("--date", help="Specify date (YYYY-MM-DD, default: latest)")
    parser.add_argument("subcommand", nargs="?", choices=["changes"], help="Subcommand (changes)")

    args = parser.parse_args()

    try:
        from olav.tools.event_tools import detect_topology_changes, query_events

        if args.subcommand == "changes":
            # Detect topology changes
            result = detect_topology_changes.invoke(
                {"time_range": args.time_range, "date": args.date}
            )
        else:
            # Query events
            params = {
                "severity_max": args.severity,
                "time_range": args.time_range,
                "date": args.date,
            }

            if args.device:
                params["device"] = args.device
            if args.type:
                params["event_type"] = args.type

            result = query_events.invoke(params)

        print(result)
        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
