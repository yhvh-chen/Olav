"""Manual E2E test runner for Standard Mode with real LLM.

Usage:
    uv run python tests/e2e/run_real_llm_tests.py

This script runs a subset of tests with real LLM calls and logs performance.
"""

import asyncio
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

# Windows async compatibility
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


# Configure logging
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "real_llm_test_results.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


# Test cases
TEST_QUERIES = [
    # Batch queries
    ("查询所有设备的接口状态", "suzieq_query", "batch_interfaces"),
    ("summarize BGP for all routers", "suzieq_query", "batch_bgp_summary"),
    
    # Single device queries
    ("查询 R1 的 BGP 状态", "suzieq_query", "single_bgp"),
    ("show interfaces on R1", "suzieq_query", "single_interfaces"),
    
    # NetBox queries
    ("列出 NetBox 中所有设备", "netbox_api_call", "netbox_list"),
    ("查询 R1 在 NetBox 中的信息", "netbox_api_call", "netbox_detail"),
    
    # Schema discovery
    ("有哪些 SuzieQ 表可用？", "suzieq_schema_search", "schema_tables"),
]


async def run_single_test(
    query: str,
    expected_tool: str,
    test_name: str,
) -> dict:
    """Run a single test and return result."""
    from olav.modes.standard import run_standard_mode
    from olav.tools.base import ToolRegistry
    
    registry = ToolRegistry()
    
    logger.info(f"=" * 60)
    logger.info(f"Test: {test_name}")
    logger.info(f"Query: {query}")
    logger.info(f"Expected tool: {expected_tool}")
    
    start = time.perf_counter()
    
    try:
        result = await run_standard_mode(
            query=query,
            tool_registry=registry,
            yolo_mode=True,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        test_result = {
            "test_name": test_name,
            "query": query,
            "expected_tool": expected_tool,
            "elapsed_ms": round(elapsed_ms, 2),
            "success": result.success,
            "escalated": result.escalated_to_expert,
            "tool_name": result.tool_name,
            "confidence": result.confidence,
            "hitl_required": result.hitl_required,
            "error": result.error,
            "answer_preview": (result.answer[:200] + "...") if result.answer and len(result.answer) > 200 else result.answer,
        }
        
    except Exception as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        test_result = {
            "test_name": test_name,
            "query": query,
            "expected_tool": expected_tool,
            "elapsed_ms": round(elapsed_ms, 2),
            "success": False,
            "error": str(e),
        }
    
    # Log result
    logger.info(f"Elapsed: {test_result['elapsed_ms']:.0f} ms")
    logger.info(f"Success: {test_result.get('success')}")
    logger.info(f"Tool: {test_result.get('tool_name')}")
    logger.info(f"Confidence: {test_result.get('confidence')}")
    if test_result.get("error"):
        logger.error(f"Error: {test_result.get('error')}")
    if test_result.get("answer_preview"):
        logger.info(f"Answer: {test_result.get('answer_preview')}")
    
    return test_result


async def main():
    """Run all tests and generate summary."""
    logger.info("=" * 80)
    logger.info(f"REAL LLM E2E TEST SESSION - {datetime.now().isoformat()}")
    logger.info("=" * 80)
    
    results = []
    
    for query, expected_tool, test_name in TEST_QUERIES:
        try:
            result = await run_single_test(query, expected_tool, test_name)
            results.append(result)
        except KeyboardInterrupt:
            logger.warning("Test interrupted by user")
            break
        except Exception as e:
            logger.error(f"Test {test_name} failed with exception: {e}")
            results.append({
                "test_name": test_name,
                "error": str(e),
                "success": False,
            })
    
    # Generate summary
    logger.info("=" * 80)
    logger.info("TEST SUMMARY")
    logger.info("=" * 80)
    
    total = len(results)
    successful = sum(1 for r in results if r.get("success"))
    escalated = sum(1 for r in results if r.get("escalated"))
    
    elapsed_times = [r.get("elapsed_ms", 0) for r in results if r.get("elapsed_ms")]
    avg_latency = sum(elapsed_times) / len(elapsed_times) if elapsed_times else 0
    max_latency = max(elapsed_times) if elapsed_times else 0
    min_latency = min(elapsed_times) if elapsed_times else 0
    
    summary = {
        "timestamp": datetime.now().isoformat(),
        "total_tests": total,
        "successful": successful,
        "success_rate": f"{100*successful/total:.1f}%" if total > 0 else "N/A",
        "escalated": escalated,
        "avg_latency_ms": round(avg_latency, 0),
        "min_latency_ms": round(min_latency, 0),
        "max_latency_ms": round(max_latency, 0),
    }
    
    logger.info(f"Total Tests: {total}")
    logger.info(f"Successful: {successful} ({summary['success_rate']})")
    logger.info(f"Escalated: {escalated}")
    logger.info(f"Latency (avg/min/max): {avg_latency:.0f} / {min_latency:.0f} / {max_latency:.0f} ms")
    
    # Save results to JSON
    json_file = LOG_DIR / "real_llm_test_results.json"
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump({
            "summary": summary,
            "results": results,
        }, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Results saved to: {json_file}")
    logger.info("=" * 80)
    
    return summary


if __name__ == "__main__":
    asyncio.run(main())
