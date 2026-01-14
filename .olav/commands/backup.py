#!/usr/bin/env python3
"""Backup network device configurations.

Usage: /backup [filter] [type] [--commands "cmd1,cmd2"]
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


def parse_filter(filter_expr: str) -> dict:
    """Parse filter expression into list_devices parameters.

    Examples:
        role:core → {"role": "core"}
        site:lab → {"site": "lab"}
        R1,R2,R3 → {"devices": ["R1", "R2", "R3"]}
        all → {}
    """
    if not filter_expr or filter_expr == "all":
        return {}

    if ":" in filter_expr:
        key, value = filter_expr.split(":", 1)
        return {key.strip(): value.strip()}

    # Device list
    return {"devices": [d.strip() for d in filter_expr.split(",")]}


def main():
    """Execute backup workflow."""
    parser = argparse.ArgumentParser(
        description="Backup network device configurations", prog="/backup"
    )
    parser.add_argument("filter", help="Device filter (role:core, site:lab, R1,R2, all)")
    parser.add_argument("type", choices=["running", "startup", "all", "custom"], help="Backup type")
    parser.add_argument("--commands", help="Custom commands (comma-separated)")

    args = parser.parse_args()

    # Validate
    if args.type == "custom" and not args.commands:
        print("Error: --commands required when type='custom'", file=sys.stderr)
        return 1

    if args.commands and args.type != "custom":
        print("Error: --commands only valid with type='custom'", file=sys.stderr)
        return 1

    try:
        # Import directly to avoid olav/__init__.py which loads deepagents
        from olav.tools.network import list_devices, nornir_execute
        from olav.tools.sync_tools import get_sync_dir, update_latest_link
        from datetime import datetime

        # Parse filter
        filter_params = parse_filter(args.filter)

        # Get device list
        if "devices" in filter_params:
            device_list = filter_params["devices"]
        else:
            result = list_devices.invoke(filter_params)
            device_list = _extract_device_names(result)

        if not device_list:
            print(f"Error: No devices found matching filter '{args.filter}'", file=sys.stderr)
            return 1

        # Determine commands
        if args.type == "custom":
            commands = [c.strip() for c in args.commands.split(",")]
        elif args.type == "all":
            commands = ["show running-config", "show startup-config"]
        else:
            commands = [f"show {args.type}-config"]

        # Execute backup to sync directory
        sync_date = datetime.now().strftime("%Y-%m-%d")
        sync_dir = get_sync_dir(sync_date)
        success_count = 0
        errors = []

        for device in device_list:
            # Create device-specific raw directory
            device_raw_dir = sync_dir / "raw" / device
            device_raw_dir.mkdir(parents=True, exist_ok=True)

            for cmd in commands:
                result = nornir_execute.invoke({"device": device, "command": cmd})

                if "Error:" in result:
                    errors.append((device, cmd, result))
                    continue

                # Determine config type and filename
                if "running-config" in cmd:
                    config_type = "running"
                    filename = "show-running-config.txt"
                elif "startup-config" in cmd:
                    config_type = "startup"
                    filename = "show-startup-config.txt"
                else:
                    config_type = "custom"
                    # Normalize command name to filename
                    cmd_safe = cmd.lower().replace(" ", "-").replace("/", "-")
                    filename = f"{cmd_safe}.txt"

                # Save raw config to data/sync/latest/raw/{device}/
                output_file = device_raw_dir / filename
                try:
                    output_file.write_text(result, encoding="utf-8")
                    success_count += 1
                except Exception as e:
                    errors.append((device, cmd, f"Failed to save: {str(e)}"))

        # Update latest link
        update_latest_link(sync_dir)

        # Summary
        print(f"\n✅ Backup Complete: {success_count} configs saved to data/sync/{sync_date}/raw/")
        if errors:
            print(f"\n❌ Errors: {len(errors)}")
            for device, cmd, error in errors:
                print(f"  - {device} ({cmd}): {error}")
            return 1

        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


def _extract_device_names(list_output: str) -> list:
    """Extract device names from list_devices output."""
    devices = []
    for line in list_output.split("\n"):
        if line.startswith("- "):
            # Parse: "- R1 (192.168.1.1) - cisco_ios - core@lab"
            dev_name = line.split()[1]
            devices.append(dev_name)
    return devices


if __name__ == "__main__":
    sys.exit(main())
