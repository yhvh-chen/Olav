#!/usr/bin/env python3
"""Run comprehensive device inspection.

Usage: /inspect [scope] [--layer L1|L2|L3|L4|all] [--report]
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Load environment
from dotenv import load_dotenv

load_dotenv()


# Inspection commands by layer
INSPECTION_COMMANDS = {
    "L1": [
        "show version",
        "show inventory",
        "show environment all",
        "show interfaces status",
    ],
    "L2": [
        "show vlan brief",
        "show spanning-tree summary",
        "show mac address-table count",
        "show cdp neighbors",
    ],
    "L3": [
        "show ip route summary",
        "show ip ospf neighbor",
        "show ip bgp summary",
        "show ip interface brief",
    ],
    "L4": [
        "show tcp brief",
        "show processes cpu sorted | head 10",
        "show memory statistics",
        "show interfaces counters errors",
    ],
}


def parse_scope(scope_expr: str) -> dict:
    """Parse scope expression into filter parameters.

    Examples:
        all → {}
        role:core → {"role": "core"}
        R1,R2,R3 → {"devices": ["R1", "R2", "R3"]}
        all core routers → {"keywords": "core routers"}
    """
    if not scope_expr or scope_expr.lower() == "all":
        return {}

    if ":" in scope_expr:
        key, value = scope_expr.split(":", 1)
        return {key.strip(): value.strip()}

    if "," in scope_expr:
        return {"devices": [d.strip() for d in scope_expr.split(",")]}

    # Natural language keywords
    return {"keywords": scope_expr}


def get_commands_for_layers(layers: list[str]) -> list[str]:
    """Get inspection commands for specified layers."""
    commands = []
    for layer in layers:
        if layer.upper() in INSPECTION_COMMANDS:
            commands.extend(INSPECTION_COMMANDS[layer.upper()])
    return commands


def format_device_result(device: str, results: list[dict]) -> str:
    """Format inspection results for a single device."""
    lines = [f"\n### {device}\n"]

    success_count = 0
    error_count = 0

    for result in results:
        cmd = result.get("command", "unknown")
        success = result.get("success", False)
        output = result.get("output", "")

        if success:
            success_count += 1
            # Truncate long output
            if len(output) > 500:
                output = output[:500] + "\n... (truncated)"
            lines.append(f"**{cmd}**")
            lines.append(f"```\n{output}\n```\n")
        else:
            error_count += 1
            lines.append(f"**{cmd}** ❌ Error: {output[:100]}\n")

    # Device summary
    status = "✅" if error_count == 0 else "⚠️" if error_count < success_count else "❌"
    lines.insert(1, f"Status: {status} ({success_count} OK, {error_count} errors)\n")

    return "\n".join(lines)


def generate_report(all_results: dict, layers: list[str], output_path: Path) -> str:
    """Generate inspection report."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        f"# Device Inspection Report ({', '.join(layers)})",
        f"\n**Inspection Time**: {timestamp}",
        f"**Total Devices**: {len(all_results)}",
        "",
    ]

    # Summary
    ok_count = 0
    warn_count = 0
    error_count = 0

    for device, results in all_results.items():
        errors = sum(1 for r in results if not r.get("success", False))
        if errors == 0:
            ok_count += 1
        elif errors < len(results) // 2:
            warn_count += 1
        else:
            error_count += 1

    lines.append(f"**Overall Status**: ✅ {ok_count} OK | ⚠️ {warn_count} Warning | ❌ {error_count} Critical\n")
    lines.append("---\n")

    # Device details
    lines.append("## Device Details\n")
    for device, results in all_results.items():
        lines.append(format_device_result(device, results))

    report_content = "\n".join(lines)

    # Save report
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report_content, encoding="utf-8")

    return report_content


def main():
    """Execute inspection workflow."""
    parser = argparse.ArgumentParser(
        description="Run comprehensive device inspection",
        prog="/inspect"
    )
    parser.add_argument("scope", nargs="*", default=["all"],
                       help="Device scope (all, role:core, R1,R2, keywords)")
    parser.add_argument("--layer", choices=["L1", "L2", "L3", "L4", "all"],
                       default="all", help="Inspection layer(s)")
    parser.add_argument("--report", action="store_true",
                       help="Generate detailed report file")

    args = parser.parse_args()

    # Parse scope
    scope_str = " ".join(args.scope)
    scope_params = parse_scope(scope_str)

    # Determine layers
    if args.layer == "all":
        layers = ["L1", "L2", "L3", "L4"]
    else:
        layers = [args.layer]

    # Get commands
    commands = get_commands_for_layers(layers)

    print(f"📋 Inspection: {scope_str}")
    print(f"   Layers: {', '.join(layers)}")
    print(f"   Commands: {len(commands)}")
    print("")

    try:
        from olav.tools.network import list_devices

        # Get device list
        if "devices" in scope_params:
            device_list = scope_params["devices"]
        else:
            result = list_devices.invoke(scope_params)
            device_list = _extract_device_names(result)

        if not device_list:
            print(f"❌ No devices found matching scope '{scope_str}'")
            return 1

        print(f"🔍 Inspecting {len(device_list)} devices: {', '.join(device_list[:5])}{'...' if len(device_list) > 5 else ''}")
        print("")

        # Execute inspection
        all_results = {}

        for device in device_list:
            print(f"  Checking {device}...")
            device_results = []

            for cmd in commands:
                try:
                    from olav.tools.network import nornir_execute
                    output = nornir_execute.invoke({"device": device, "command": cmd})
                    success = "Error:" not in output
                    device_results.append({
                        "command": cmd,
                        "success": success,
                        "output": output
                    })
                except Exception as e:
                    device_results.append({
                        "command": cmd,
                        "success": False,
                        "output": str(e)
                    })

            all_results[device] = device_results

            # Print quick status
            errors = sum(1 for r in device_results if not r["success"])
            status = "✅" if errors == 0 else "⚠️" if errors < len(commands) // 2 else "❌"
            print(f"    {status} {len(commands) - errors}/{len(commands)} commands OK")

        # Generate report if requested
        if args.report:
            from config.settings import settings
            report_path = Path(settings.agent_dir) / "data" / "reports" / f"inspection-{datetime.now().strftime('%Y%m%d-%H%M%S')}.md"
            generate_report(all_results, layers, report_path)
            print(f"\n📄 Report saved: {report_path}")
        else:
            # Print summary
            print("\n" + "=" * 60)
            print("INSPECTION SUMMARY")
            print("=" * 60)

            for device, results in all_results.items():
                errors = sum(1 for r in results if not r["success"])
                status = "✅" if errors == 0 else "⚠️" if errors < len(results) // 2 else "❌"
                print(f"  {status} {device}: {len(results) - errors}/{len(results)} OK")

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
            parts = line.split()
            if len(parts) >= 2:
                devices.append(parts[1])
    return devices


if __name__ == "__main__":
    sys.exit(main())
