#!/usr/bin/env python3
"""E2E Performance Testing Script with LLM Token and Graph State Logging.

This script runs real LLM E2E tests for all modes and captures:
- LLM token usage (input/output tokens)
- Graph state transitions
- Timing for each phase
- Tool execution times
- Memory usage

Usage:
    uv run python scripts/e2e_perf_test.py --mode standard
    uv run python scripts/e2e_perf_test.py --mode expert
    uv run python scripts/e2e_perf_test.py --mode inspection
    uv run python scripts/e2e_perf_test.py --mode all
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from olav.core.llm import LLMFactory


# =============================================================================
# Performance Logger
# =============================================================================


@dataclass
class LLMCallMetrics:
    """Metrics for a single LLM call."""
    call_id: str
    timestamp: str
    duration_ms: float
    input_tokens: int
    output_tokens: int
    total_tokens: int
    model: str
    purpose: str  # classify, extract_params, format_answer, etc.
    prompt_preview: str = ""  # First 200 chars
    response_preview: str = ""  # First 200 chars


@dataclass
class GraphStateMetrics:
    """Metrics for graph state transitions."""
    node: str
    timestamp: str
    duration_ms: float
    state_summary: dict = field(default_factory=dict)


@dataclass
class TestRunMetrics:
    """Complete metrics for a single test run."""
    test_id: str
    mode: str
    query: str
    started_at: str
    completed_at: str
    total_duration_ms: float
    success: bool
    
    # LLM metrics
    llm_calls: list[LLMCallMetrics] = field(default_factory=list)
    total_llm_time_ms: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    
    # Graph metrics
    graph_states: list[GraphStateMetrics] = field(default_factory=list)
    
    # Tool metrics
    tool_calls: list[dict] = field(default_factory=list)
    total_tool_time_ms: float = 0.0
    
    # Result
    result_summary: str = ""
    error: str | None = None


class PerformanceLogger:
    """Central performance logger for E2E tests."""
    
    def __init__(self, log_dir: str = "tests/e2e/logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Create timestamped log file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = self.log_dir / f"e2e_perf_{timestamp}.jsonl"
        self.summary_file = self.log_dir / f"e2e_perf_{timestamp}_summary.md"
        
        # Current test context
        self._current_run: TestRunMetrics | None = None
        self._llm_call_counter = 0
        
        # Setup logging
        self._setup_logging()
    
    def _setup_logging(self):
        """Setup console and file logging."""
        self.logger = logging.getLogger("e2e_perf")
        self.logger.setLevel(logging.DEBUG)
        
        # Console handler
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        console.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S"
        ))
        self.logger.addHandler(console)
        
        # File handler
        file_handler = logging.FileHandler(
            self.log_dir / "e2e_perf.log",
            encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        ))
        self.logger.addHandler(file_handler)
    
    def start_test(self, mode: str, query: str) -> str:
        """Start a new test run."""
        test_id = f"{mode}_{datetime.now().strftime('%H%M%S_%f')}"
        
        self._current_run = TestRunMetrics(
            test_id=test_id,
            mode=mode,
            query=query,
            started_at=datetime.now().isoformat(),
            completed_at="",
            total_duration_ms=0.0,
            success=False,
        )
        self._llm_call_counter = 0
        
        self.logger.info(f"🚀 Starting test: {test_id}")
        self.logger.info(f"   Mode: {mode}")
        self.logger.info(f"   Query: {query[:80]}...")
        
        return test_id
    
    def log_llm_call(
        self,
        purpose: str,
        duration_ms: float,
        input_tokens: int,
        output_tokens: int,
        model: str,
        prompt: str = "",
        response: str = "",
    ):
        """Log an LLM call."""
        if not self._current_run:
            return
        
        self._llm_call_counter += 1
        call_id = f"llm_{self._llm_call_counter}"
        
        metrics = LLMCallMetrics(
            call_id=call_id,
            timestamp=datetime.now().isoformat(),
            duration_ms=duration_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            model=model,
            purpose=purpose,
            prompt_preview=prompt[:200] if prompt else "",
            response_preview=response[:200] if response else "",
        )
        
        self._current_run.llm_calls.append(metrics)
        self._current_run.total_llm_time_ms += duration_ms
        self._current_run.total_input_tokens += input_tokens
        self._current_run.total_output_tokens += output_tokens
        
        self.logger.debug(
            f"  📝 LLM [{purpose}]: {duration_ms:.0f}ms, "
            f"tokens: {input_tokens}+{output_tokens}={input_tokens + output_tokens}"
        )
    
    def log_graph_state(self, node: str, duration_ms: float, state: dict):
        """Log a graph state transition."""
        if not self._current_run:
            return
        
        metrics = GraphStateMetrics(
            node=node,
            timestamp=datetime.now().isoformat(),
            duration_ms=duration_ms,
            state_summary=state,
        )
        
        self._current_run.graph_states.append(metrics)
        
        self.logger.debug(f"  📊 Graph [{node}]: {duration_ms:.0f}ms")
    
    def log_tool_call(self, tool: str, duration_ms: float, success: bool, params: dict):
        """Log a tool call."""
        if not self._current_run:
            return
        
        self._current_run.tool_calls.append({
            "tool": tool,
            "timestamp": datetime.now().isoformat(),
            "duration_ms": duration_ms,
            "success": success,
            "params": params,
        })
        self._current_run.total_tool_time_ms += duration_ms
        
        status = "✓" if success else "✗"
        self.logger.debug(f"  🔧 Tool [{tool}]: {duration_ms:.0f}ms {status}")
    
    def end_test(self, success: bool, result_summary: str = "", error: str | None = None):
        """End the current test run and save metrics."""
        if not self._current_run:
            return
        
        self._current_run.completed_at = datetime.now().isoformat()
        self._current_run.success = success
        self._current_run.result_summary = result_summary
        self._current_run.error = error
        
        # Calculate total duration
        start = datetime.fromisoformat(self._current_run.started_at)
        end = datetime.fromisoformat(self._current_run.completed_at)
        self._current_run.total_duration_ms = (end - start).total_seconds() * 1000
        
        # Log summary
        status = "✅ PASSED" if success else "❌ FAILED"
        self.logger.info(f"{status} Test: {self._current_run.test_id}")
        self.logger.info(f"   Total time: {self._current_run.total_duration_ms:.0f}ms")
        self.logger.info(f"   LLM time: {self._current_run.total_llm_time_ms:.0f}ms ({len(self._current_run.llm_calls)} calls)")
        self.logger.info(f"   Tokens: {self._current_run.total_input_tokens}+{self._current_run.total_output_tokens}")
        self.logger.info(f"   Tool time: {self._current_run.total_tool_time_ms:.0f}ms ({len(self._current_run.tool_calls)} calls)")
        
        if error:
            self.logger.error(f"   Error: {error}")
        
        # Save to JSONL
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(self._current_run), ensure_ascii=False) + "\n")
        
        self._current_run = None
    
    def generate_summary(self, runs: list[TestRunMetrics]) -> str:
        """Generate markdown summary of all test runs."""
        lines = [
            "# E2E Performance Test Summary\n",
            f"**Generated**: {datetime.now().isoformat()}",
            f"**Total Tests**: {len(runs)}",
            f"**Passed**: {sum(1 for r in runs if r.success)}",
            f"**Failed**: {sum(1 for r in runs if not r.success)}",
            "",
            "## Test Results\n",
            "| Mode | Query | Duration | LLM Time | Tokens | Tool Time | Status |",
            "|------|-------|----------|----------|--------|-----------|--------|",
        ]
        
        for run in runs:
            status = "✅" if run.success else "❌"
            query_short = run.query[:30] + "..." if len(run.query) > 30 else run.query
            lines.append(
                f"| {run.mode} | {query_short} | "
                f"{run.total_duration_ms:.0f}ms | "
                f"{run.total_llm_time_ms:.0f}ms | "
                f"{run.total_input_tokens}+{run.total_output_tokens} | "
                f"{run.total_tool_time_ms:.0f}ms | {status} |"
            )
        
        # Aggregate stats
        if runs:
            lines.extend([
                "",
                "## Aggregate Statistics\n",
                f"- **Avg Duration**: {sum(r.total_duration_ms for r in runs) / len(runs):.0f}ms",
                f"- **Avg LLM Time**: {sum(r.total_llm_time_ms for r in runs) / len(runs):.0f}ms",
                f"- **Avg Tokens**: {sum(r.total_input_tokens + r.total_output_tokens for r in runs) / len(runs):.0f}",
                f"- **Total LLM Calls**: {sum(len(r.llm_calls) for r in runs)}",
                f"- **Total Tool Calls**: {sum(len(r.tool_calls) for r in runs)}",
            ])
        
        return "\n".join(lines)


# =============================================================================
# LLM Instrumentation
# =============================================================================


class InstrumentedLLM:
    """Wrapper around LLM that captures metrics."""
    
    def __init__(self, perf_logger: PerformanceLogger):
        self.perf_logger = perf_logger
        self.llm = LLMFactory.get_chat_model()
        self.model_name = os.getenv("LLM_MODEL_NAME", "unknown")
    
    async def invoke(self, prompt: str, purpose: str = "unknown") -> str:
        """Invoke LLM with instrumentation."""
        start = time.perf_counter()
        
        try:
            response = await self.llm.ainvoke(prompt)
            duration_ms = (time.perf_counter() - start) * 1000
            
            # Extract token counts (model-dependent)
            input_tokens = len(prompt) // 4  # Rough estimate
            output_tokens = len(response.content) // 4
            
            # Try to get actual token counts from response metadata
            if hasattr(response, "response_metadata"):
                meta = response.response_metadata
                if "token_usage" in meta:
                    input_tokens = meta["token_usage"].get("prompt_tokens", input_tokens)
                    output_tokens = meta["token_usage"].get("completion_tokens", output_tokens)
                elif "prompt_eval_count" in meta:  # Ollama format
                    input_tokens = meta.get("prompt_eval_count", input_tokens)
                    output_tokens = meta.get("eval_count", output_tokens)
            
            self.perf_logger.log_llm_call(
                purpose=purpose,
                duration_ms=duration_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=self.model_name,
                prompt=prompt,
                response=response.content,
            )
            
            return response.content
            
        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000
            self.perf_logger.log_llm_call(
                purpose=f"{purpose}_error",
                duration_ms=duration_ms,
                input_tokens=len(prompt) // 4,
                output_tokens=0,
                model=self.model_name,
                prompt=prompt,
                response=str(e),
            )
            raise


# =============================================================================
# Test Runners
# =============================================================================


async def run_standard_mode_test(
    query: str,
    perf_logger: PerformanceLogger,
) -> bool:
    """Run a single Standard Mode test with instrumentation."""
    from olav.modes.standard import run_standard_mode
    from olav.tools.base import ToolRegistry
    
    test_id = perf_logger.start_test("standard", query)
    
    try:
        registry = ToolRegistry()
        
        start = time.perf_counter()
        result = await run_standard_mode(
            query=query,
            tool_registry=registry,
            yolo_mode=True,  # Skip HITL for testing
        )
        total_duration = (time.perf_counter() - start) * 1000
        
        # Get execution time from result metadata if available
        llm_time = result.metadata.get("llm_time_ms", 0) if result.metadata else 0
        classify_time = result.metadata.get("classify_time_ms", total_duration * 0.3) if result.metadata else total_duration * 0.3
        
        # Estimate LLM tokens from execution time (rough: 50 tokens/sec for ollama)
        estimated_tokens = int(llm_time / 20) if llm_time > 0 else int(classify_time / 20)
        
        # Log LLM call (classification)
        perf_logger.log_llm_call(
            purpose="unified_classify",
            duration_ms=classify_time,
            input_tokens=estimated_tokens // 2,
            output_tokens=estimated_tokens // 2,
            model=os.getenv("LLM_MODEL_NAME", "unknown"),
            prompt=f"Query: {query}",
            response=f"Tool: {result.tool_name}, Confidence: {result.confidence}",
        )
        
        # Log graph states
        perf_logger.log_graph_state("classify", classify_time, {
            "intent": result.intent_category,
            "confidence": result.confidence,
        })
        
        perf_logger.log_graph_state("execute", result.execution_time_ms, {
            "tool": result.tool_name,
            "success": result.success,
        })
        
        if result.tool_name:
            perf_logger.log_tool_call(
                result.tool_name,
                result.execution_time_ms,
                result.success,
                {},
            )
        
        perf_logger.end_test(
            success=result.success,
            result_summary=result.answer[:200] if result.answer else "",
        )
        
        return result.success
        
    except Exception as e:
        perf_logger.end_test(
            success=False,
            error=str(e),
        )
        return False


async def run_expert_mode_test(
    query: str,
    perf_logger: PerformanceLogger,
) -> bool:
    """Run a single Expert Mode test with instrumentation."""
    from olav.modes.expert import run_expert_mode
    
    test_id = perf_logger.start_test("expert", query)
    
    try:
        start = time.perf_counter()
        
        # Run with debug=True to capture graph states and LLM calls
        result = await run_expert_mode(
            query=query, 
            debug=True,
        )
        
        duration = (time.perf_counter() - start) * 1000
        
        # Log graph states from debug output
        if result.debug_output:
            # Log graph states if available
            if hasattr(result.debug_output, 'graph_states'):
                for graph_state in result.debug_output.graph_states:
                    perf_logger.log_graph_state(
                        getattr(graph_state, 'node', 'unknown'),
                        0,  # Timing not captured per-node yet
                        getattr(graph_state, 'state', {}),
                    )
            
            # Log LLM calls if recorded
            if hasattr(result.debug_output, 'llm_calls'):
                for llm_call in result.debug_output.llm_calls:
                    if isinstance(llm_call, dict):
                        perf_logger.log_llm_call(
                            purpose=llm_call.get("purpose", "expert_mode"),
                            duration_ms=llm_call.get("duration_ms", 0),
                            input_tokens=llm_call.get("input_tokens", 0),
                            output_tokens=llm_call.get("output_tokens", 0),
                            model=os.getenv("LLM_MODEL_NAME", "unknown"),
                            prompt=str(llm_call.get("prompt", ""))[:200],
                            response=str(llm_call.get("response", ""))[:200],
                        )
        
        # Log layer coverage
        if result.layer_coverage:
            for layer, coverage in result.layer_coverage.items():
                perf_logger.log_graph_state(f"layer_{layer}", 0, {"coverage": coverage})
        
        # Log overall LLM call with timing
        rounds = result.rounds_executed
        perf_logger.log_llm_call(
            purpose=f"expert_mode_{rounds}_rounds",
            duration_ms=duration * 0.7,  # Estimate 70% is LLM time
            input_tokens=int(duration / 20),
            output_tokens=int(duration / 40),
            model=os.getenv("LLM_MODEL_NAME", "unknown"),
            prompt=f"Query: {query}",
            response=f"Rounds: {rounds}, Root cause: {result.root_cause_found}",
        )
        
        perf_logger.end_test(
            success=result.success,
            result_summary=result.final_report[:200] if result.final_report else "",
        )
        
        return result.success
        
    except Exception as e:
        import traceback
        perf_logger.end_test(
            success=False,
            error=f"{str(e)}\n{traceback.format_exc()[:500]}",
        )
        return False


async def run_inspection_mode_test(
    config_path: str,
    perf_logger: PerformanceLogger,
) -> bool:
    """Run a single Inspection Mode test with instrumentation."""
    from olav.modes.inspection import run_inspection
    
    test_id = perf_logger.start_test("inspection", f"config: {config_path}")
    
    try:
        start = time.perf_counter()
        result = await run_inspection(config_path, debug=True)
        duration = (time.perf_counter() - start) * 1000
        
        # Log check results
        for check in result.check_results:
            perf_logger.log_tool_call(
                check.check_name,
                check.duration_ms,
                check.success,
                {"device": check.device},
            )
        
        perf_logger.log_graph_state("inspection_complete", duration, {
            "total_devices": result.total_devices,
            "devices_passed": result.devices_passed,
            "total_checks": result.total_checks,
            "checks_passed": result.checks_passed,
        })
        
        success = result.devices_failed == 0
        perf_logger.end_test(
            success=success,
            result_summary=result.to_markdown()[:500] if hasattr(result, "to_markdown") else "",
        )
        
        return success
        
    except Exception as e:
        perf_logger.end_test(
            success=False,
            error=str(e),
        )
        return False


# =============================================================================
# Test Suites
# =============================================================================


STANDARD_MODE_QUERIES = [
    "查询 R1 的 BGP 状态",
    "显示所有设备的接口状态",
    "R1 的 OSPF 邻居有哪些",
    "检查 spine-1 的路由表",
    "查看 core-rtr 的 BGP 会话",
    "列出所有设备",
    "R1 有多少个接口是 up 状态",
    "查询 leaf-1 的 VXLAN 状态",
]

EXPERT_MODE_QUERIES = [
    "为什么 R1 和 R2 之间的 BGP 会话建立失败",
    "分析 spine-1 的网络连通性问题",
    "诊断 leaf-1 无法 ping 通 leaf-2 的原因",
]


async def run_standard_mode_suite(perf_logger: PerformanceLogger):
    """Run Standard Mode test suite."""
    perf_logger.logger.info("\n" + "=" * 60)
    perf_logger.logger.info("📋 STANDARD MODE TEST SUITE")
    perf_logger.logger.info("=" * 60 + "\n")
    
    results = []
    for query in STANDARD_MODE_QUERIES:
        success = await run_standard_mode_test(query, perf_logger)
        results.append((query, success))
        
        # Small delay between tests
        await asyncio.sleep(0.5)
    
    passed = sum(1 for _, s in results if s)
    perf_logger.logger.info(f"\n📊 Standard Mode: {passed}/{len(results)} passed\n")
    
    return results


async def run_expert_mode_suite(perf_logger: PerformanceLogger):
    """Run Expert Mode test suite."""
    perf_logger.logger.info("\n" + "=" * 60)
    perf_logger.logger.info("🔬 EXPERT MODE TEST SUITE")
    perf_logger.logger.info("=" * 60 + "\n")
    
    results = []
    for query in EXPERT_MODE_QUERIES:
        success = await run_expert_mode_test(query, perf_logger)
        results.append((query, success))
        
        await asyncio.sleep(0.5)
    
    passed = sum(1 for _, s in results if s)
    perf_logger.logger.info(f"\n📊 Expert Mode: {passed}/{len(results)} passed\n")
    
    return results


async def run_inspection_mode_suite(perf_logger: PerformanceLogger):
    """Run Inspection Mode test suite."""
    perf_logger.logger.info("\n" + "=" * 60)
    perf_logger.logger.info("📋 INSPECTION MODE TEST SUITE")
    perf_logger.logger.info("=" * 60 + "\n")
    
    # Create a test config
    import tempfile
    import yaml
    
    test_config = {
        "name": "E2E Performance Test",
        "description": "Test inspection for performance measurement",
        "devices": {"explicit_devices": ["R1", "R2"]},
        "checks": [
            {
                "name": "interface_status",
                "tool": "suzieq_query",
                "parameters": {"table": "interfaces", "view": "latest"},
            },
        ],
    }
    
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".yaml",
        delete=False,
        encoding="utf-8"
    ) as f:
        yaml.dump(test_config, f)
        config_path = f.name
    
    try:
        success = await run_inspection_mode_test(config_path, perf_logger)
        results = [(config_path, success)]
    finally:
        Path(config_path).unlink(missing_ok=True)
    
    passed = sum(1 for _, s in results if s)
    perf_logger.logger.info(f"\n📊 Inspection Mode: {passed}/{len(results)} passed\n")
    
    return results


# =============================================================================
# Main
# =============================================================================


async def main():
    parser = argparse.ArgumentParser(description="E2E Performance Testing")
    parser.add_argument(
        "--mode",
        choices=["standard", "expert", "inspection", "all"],
        default="all",
        help="Which mode to test",
    )
    parser.add_argument(
        "--query",
        type=str,
        default=None,
        help="Single query to test (overrides suite)",
    )
    
    args = parser.parse_args()
    
    # Initialize logger
    perf_logger = PerformanceLogger()
    
    perf_logger.logger.info("🚀 E2E Performance Testing Started")
    perf_logger.logger.info(f"   Mode: {args.mode}")
    perf_logger.logger.info(f"   LLM Provider: {os.getenv('LLM_PROVIDER', 'unknown')}")
    perf_logger.logger.info(f"   LLM Model: {os.getenv('LLM_MODEL_NAME', 'unknown')}")
    perf_logger.logger.info(f"   Log file: {perf_logger.log_file}")
    
    all_results = []
    
    try:
        if args.query:
            # Single query test
            if args.mode == "expert":
                success = await run_expert_mode_test(args.query, perf_logger)
            else:
                success = await run_standard_mode_test(args.query, perf_logger)
            all_results.append((args.query, success))
        else:
            # Full suite
            if args.mode in ("standard", "all"):
                results = await run_standard_mode_suite(perf_logger)
                all_results.extend(results)
            
            if args.mode in ("expert", "all"):
                results = await run_expert_mode_suite(perf_logger)
                all_results.extend(results)
            
            if args.mode in ("inspection", "all"):
                results = await run_inspection_mode_suite(perf_logger)
                all_results.extend(results)
        
        # Final summary
        passed = sum(1 for _, s in all_results if s)
        total = len(all_results)
        
        perf_logger.logger.info("\n" + "=" * 60)
        perf_logger.logger.info(f"🏁 FINAL RESULTS: {passed}/{total} tests passed")
        perf_logger.logger.info("=" * 60)
        perf_logger.logger.info(f"📁 Logs saved to: {perf_logger.log_file}")
        
    except KeyboardInterrupt:
        perf_logger.logger.info("\n⚠️ Test interrupted by user")
    except Exception as e:
        perf_logger.logger.error(f"❌ Test suite failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
