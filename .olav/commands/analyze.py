#!/usr/bin/env python3
"""Analyze network path from source to destination.

Usage: /analyze [source] [destination] [--error "desc"] [--plan] [--interactive]
"""
import argparse
import re
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Load environment
from dotenv import load_dotenv

load_dotenv()


def show_plan(source: str, destination: str, error_desc: str = None) -> str:
    """Show analysis plan for user confirmation."""
    plan = f"""## Analysis Plan: {source} → {destination}

### Phase 1: Macro Analysis (macro-analyzer)
Goal: Trace path and identify fault domain
Steps:
  1. Execute traceroute from {source} to {destination}
  2. Check BGP/OSPF neighbor status on all path devices
  3. Identify intermediate devices and their status
  4. Determine fault domain

### Phase 2: Micro Analysis (micro-analyzer)
Goal: Layer-by-layer troubleshooting on problem device
Steps:
  1. Physical layer check (interface status, CRC errors)
  2. Data link layer check (VLAN, MAC table, STP)
  3. Network layer check (IP, routing, ARP)
  4. Transport layer check (ACLs, NAT)
  5. Application layer check (DNS, services)

### Phase 3: Synthesis
Goal: Combine findings and provide recommendations
"""
    if error_desc:
        plan += f"\n### Error Context\n{error_desc}\n"

    return plan


def extract_problem_device(macro_result: str) -> str:
    """Extract problem device from macro analysis result."""
    patterns = [
        r'Problem device:\s*(\w+)',
        r'Issue found on:\s*(\w+)',
        r'Fault domain:\s*(\w+)',
    ]

    for pattern in patterns:
        match = re.search(pattern, macro_result, re.IGNORECASE)
        if match:
            return match.group(1)

    return None


def synthesize_results(macro_result: str, micro_result: str) -> str:
    """Synthesize macro and micro analysis results."""
    return f"""## Analysis Synthesis

### Macro Analysis Summary
{macro_result[:500]}...

### Micro Analysis Summary
{micro_result[:500]}...

### Root Cause Analysis
[Combined analysis]

### Recommendations
1. [Actionable recommendation 1]
2. [Actionable recommendation 2]
3. [Actionable recommendation 3]
"""


def main():
    """Execute analysis workflow."""
    parser = argparse.ArgumentParser(
        description="Analyze network path from source to destination",
        prog="/analyze"
    )
    parser.add_argument("source", help="Source device name")
    parser.add_argument("destination", help="Destination device name")
    parser.add_argument("--error", help="Error description to guide analysis")
    parser.add_argument("--plan", action="store_true",
                       help="Show analysis plan before execution")
    parser.add_argument("--interactive", action="store_true",
                       help="Pause after each analysis phase")

    args = parser.parse_args()

    # Show plan if requested
    if args.plan:
        plan = show_plan(args.source, args.destination, args.error)
        print(plan)

        confirmation = input("\nExecute this plan? (yes/no): ").strip().lower()
        if confirmation not in ["yes", "y"]:
            print("Analysis cancelled by user")
            return 0

        print("\n" + "="*60 + "\n")

    try:
        from olav.tools.task_tools import delegate_task

        # Prepare task description
        base_task = f"Analyze network path from {args.source} to {args.destination}"
        if args.error:
            task_desc = f"{base_task}\n\nError Context: {args.error}"
        else:
            task_desc = base_task

        # Phase 1: Macro Analysis
        print("=== Phase 1: Macro Analysis ===\n")
        macro_task = f"""{task_desc}

Please perform macro analysis:
1. Trace the path from {args.source} to {args.destination}
2. Identify all intermediate devices
3. Check BGP/OSPF neighbor status
4. Determine fault domain

Provide a structured report with:
- Path trace results
- Device status
- Identified fault domain
"""

        macro_result = delegate_task.invoke({
            "subagent_type": "macro-analyzer",
            "task_description": macro_task
        })

        print(macro_result)

        if args.interactive:
            input("\n[Paused] Press Enter to continue to Phase 2...")
            print("\n" + "="*60 + "\n")

        # Phase 2: Micro Analysis
        print("=== Phase 2: Micro Analysis ===\n")
        problem_device = extract_problem_device(macro_result) or args.source

        micro_task = f"""Perform TCP/IP layer-by-layer troubleshooting on {problem_device}

Error context: {args.error if args.error else "Not specified"}

Please analyze:
1. Physical layer: interface status, CRC errors, optical power
2. Data link layer: VLAN, MAC table, STP
3. Network layer: IP configuration, routing, ARP
4. Transport layer: ACLs, NAT, port filtering
5. Application layer: DNS, services

Provide a structured report with findings for each layer.
"""

        micro_result = delegate_task.invoke({
            "subagent_type": "micro-analyzer",
            "task_description": micro_task
        })

        print(micro_result)

        if args.interactive:
            input("\n[Paused] Press Enter to continue to Phase 3...")
            print("\n" + "="*60 + "\n")

        # Phase 3: Synthesis
        print("=== Phase 3: Synthesis ===\n")
        synthesis = synthesize_results(macro_result, micro_result)
        print(synthesis)

        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
