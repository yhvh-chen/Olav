"""
Expert Mode Accuracy Test - Real Network Diagnosis.

Tests diagnostic accuracy with a specific network scenario.
"""

import asyncio
import logging
import time

# Set logging to INFO to reduce verbosity
logging.basicConfig(level=logging.INFO, format='%(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def test_expert_accuracy():
    from olav.modes.expert import run_expert_mode
    
    # Realistic user report - more typical of real-world troubleshooting scenarios
    query = "用户报告他们的主机192.168.10.1/24无法访问IOT设备10.0.100.100/16，请查明原因"
    
    print("=" * 80)
    print("EXPERT MODE ACCURACY TEST")
    print("=" * 80)
    print(f"\nQuery: {query}")
    print("\n" + "-" * 80)
    print("Running Expert Mode diagnosis...")
    print("-" * 80 + "\n")
    
    start = time.perf_counter()
    
    result = await run_expert_mode(
        query=query,
        max_rounds=5,  # Allow more rounds for thorough analysis
        debug=True,
    )
    
    elapsed = (time.perf_counter() - start) * 1000
    
    print("\n" + "=" * 80)
    print("DIAGNOSIS RESULTS")
    print("=" * 80)
    
    print(f"\n⏱️  Total Time: {elapsed:.0f} ms ({elapsed/1000:.1f} seconds)")
    print(f"✅ Success: {result.success}")
    print(f"🔄 Rounds Executed: {result.rounds_executed}")
    print(f"🎯 Root Cause Found: {result.root_cause_found}")
    
    print("\n" + "-" * 80)
    print("LAYER COVERAGE")
    print("-" * 80)
    for layer, coverage in result.layer_coverage.items():
        conf = coverage.get("confidence", 0)
        findings = len(coverage.get("findings", []))
        status = "✅" if conf >= 80 else "⚠️" if conf >= 50 else "⬜"
        print(f"  {status} {layer}: {conf}% confidence, {findings} findings")
    
    if result.root_cause:
        print("\n" + "-" * 80)
        print("ROOT CAUSE ANALYSIS")
        print("-" * 80)
        print(result.root_cause)
    
    print("\n" + "-" * 80)
    print("FINAL REPORT")
    print("-" * 80)
    print(result.final_report)
    
    # Debug output if available
    if result.debug_output:
        print("\n" + "-" * 80)
        print("DEBUG INFO")
        print("-" * 80)
        if hasattr(result.debug_output, "llm_calls"):
            print(f"LLM Calls: {len(result.debug_output.llm_calls)}")
        if hasattr(result.debug_output, "tool_calls"):
            print(f"Tool Calls: {len(result.debug_output.tool_calls)}")
    
    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_expert_accuracy())
