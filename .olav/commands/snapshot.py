#!/usr/bin/env python3
"""Network snapshot - Collect network data from devices.

Usage:
    /snapshot              # Snapshot all devices
    /snapshot R1,R2,R3     # Snapshot specified devices
"""

import argparse
import sys
from pathlib import Path

# Add project root to path for olav imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

# Load environment
from dotenv import load_dotenv

load_dotenv()


def main():
    """Execute sync workflow."""
    parser = argparse.ArgumentParser(
        description="Network sync - Collect network data",
        prog="/sync"
    )
    parser.add_argument(
        "devices",
        nargs="?",
        default="all",
        help="Device filter: 'all' or comma-separated list (R1,R2,R3)"
    )

    args = parser.parse_args()

    try:
        from olav.tools.sync_tools import sync_all

        # Execute sync
        result = sync_all.invoke({"devices": args.devices})

        print(result)
        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
