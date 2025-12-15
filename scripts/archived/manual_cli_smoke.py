"""Manual smoke test for CLI Agent & fallback flow.

Usage (PowerShell):
  uv run python scripts/manual_cli_smoke.py --device R1

This script exercises:
1. NETCONF attempt (expected failure triggers fallback hint)
2. CLI read command with TextFSM parsing
3. CLI blacklisted command interception
4. CLI configuration command (simulated HITL approve / reject)

Prerequisites:
- NetBox inventory contains the target device (tag: olav-managed)
- Environment variables (POSTGRES_URI, NETBOX_URL, NETBOX_TOKEN, DEVICE_USERNAME, DEVICE_PASSWORD) are set
- Optional: create command_blacklist.txt to extend blacklist
"""
from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from olav.tools.nornir_tool import netconf_tool, cli_tool

async def run(device: str, approve: bool) -> None:
    print("\n[1] NETCONF get-config attempt (should fail on non-NETCONF devices)")
    netconf_res = await netconf_tool(device=device, operation="get-config", xpath="/interfaces/interface/state")
    print(json.dumps(netconf_res, indent=2, ensure_ascii=False))
    if not netconf_res.get("success"):
        print("➡ Detected NETCONF failure; proceed with CLI fallback")

    print("\n[2] CLI read command (interface brief)")
    cli_read = await cli_tool(device=device, command="show ip interface brief")
    print(json.dumps(cli_read, indent=2, ensure_ascii=False))

    print("\n[3] CLI blacklist interception (traceroute)")
    cli_blk = await cli_tool(device=device, command="traceroute 8.8.8.8")
    print(json.dumps(cli_blk, indent=2, ensure_ascii=False))

    print("\n[4] CLI config command (MTU change) with simulated HITL decision")
    # NOTE: HITL middleware currently auto-approves; simulation via approve flag
    if approve:
        config_cmds = ["interface GigabitEthernet0/0", "mtu 9000"]
        cfg_res = await cli_tool(device=device, config_commands=config_cmds)
    else:
        # Simulate rejection by short-circuiting expected result
        cfg_res = {"success": False, "error": "Configuration rejected (simulated)", "commands": ["interface GigabitEthernet0/0", "mtu 9000"]}
    print(json.dumps(cfg_res, indent=2, ensure_ascii=False))

    print("\nSummary:")
    summary = {
        "netconf_success": netconf_res.get("success"),
        "cli_parsed": cli_read.get("parsed"),
        "blacklist_blocked": not cli_blk.get("success"),
        "config_success": cfg_res.get("success"),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="CLI smoke test")
    parser.add_argument("--device", required=True, help="Target device hostname")
    parser.add_argument("--reject", action="store_true", help="Simulate HITL reject for config")
    args = parser.parse_args()
    asyncio.run(run(device=args.device, approve=not args.reject))

if __name__ == "__main__":
    main()
