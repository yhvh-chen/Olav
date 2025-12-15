"""
Expert Mode E2E Performance Test with Real LLM.

Tests diagnostic queries to measure performance after optimization.
"""

import asyncio
import time
import sys


async def test_expert_mode():
    from olav.modes.expert import run_expert_mode
    
    queries = [
        "为什么 R1 和 R2 之间 BGP 断了",
        "诊断 spine-1 连通性问题",
        "Why is BGP down between core-1 and edge-1",
    ]
    
    results = []
    
    for query in queries:
        print(f"\n{'='*60}")
        print(f"Query: {query}")
        print("=" * 60)
        
        start = time.perf_counter()
        try:
            result = await run_expert_mode(
                query=query,
                max_rounds=3,
                debug=True,
            )
            elapsed = (time.perf_counter() - start) * 1000
            
            print(f"Elapsed: {elapsed:.0f} ms")
            print(f"Success: {result.success}")
            print(f"Rounds: {result.rounds_executed}")
            print(f"Root Cause Found: {result.root_cause_found}")
            if result.root_cause:
                rc = result.root_cause[:200] + "..." if len(result.root_cause) > 200 else result.root_cause
                print(f"Root Cause: {rc}")
            if result.final_report:
                report = result.final_report[:300] + "..." if len(result.final_report) > 300 else result.final_report
                print(f"Report: {report}")
            
            results.append({
                "query": query,
                "elapsed_ms": elapsed,
                "success": result.success,
                "rounds": result.rounds_executed,
                "root_cause_found": result.root_cause_found,
            })
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            results.append({
                "query": query,
                "elapsed_ms": elapsed,
                "success": False,
                "error": str(e),
            })
    
    print(f"\n{'='*60}")
    print("SUMMARY")
    print("=" * 60)
    for r in results:
        status = "OK" if r.get("success") else "FAIL"
        query_short = r["query"][:40]
        print(f"[{status}] {r['elapsed_ms']:.0f}ms - {query_short}")
    
    avg_time = sum(r["elapsed_ms"] for r in results) / len(results)
    success_count = sum(1 for r in results if r.get("success"))
    print(f"\nAverage: {avg_time:.0f} ms")
    print(f"Success: {success_count}/{len(results)}")


if __name__ == "__main__":
    asyncio.run(test_expert_mode())
