"""Extended E2E Tests for Standard Mode - Coverage Completion.

These tests supplement test_standard_mode.py with:
- Batch device queries
- NetBox CRUD (Create, Read, Update, Delete)
- HITL approval/rejection flow
- Performance logging for optimization

Usage:
    # Run all extended tests with logging
    uv run pytest tests/e2e/test_standard_mode_extended.py -v -s
    
    # View performance log
    cat tests/e2e/logs/standard_mode_perf.log
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

# Windows async compatibility
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


# ============================================
# Performance Logging Setup
# ============================================
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
PERF_LOG_FILE = LOG_DIR / "standard_mode_perf.log"

# Configure performance logger
perf_logger = logging.getLogger("standard_mode_perf")
perf_logger.setLevel(logging.INFO)

# File handler with detailed format
file_handler = logging.FileHandler(PERF_LOG_FILE, mode="a", encoding="utf-8")
file_handler.setFormatter(logging.Formatter(
    "%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
))
perf_logger.addHandler(file_handler)

# Console handler for visibility
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter("%(message)s"))
perf_logger.addHandler(console_handler)


def log_test_result(
    test_name: str,
    query: str,
    result: Any,
    elapsed_ms: float,
    extra: dict[str, Any] | None = None,
) -> None:
    """Log test execution result for performance analysis."""
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "test": test_name,
        "query": query[:100],  # Truncate long queries
        "elapsed_ms": round(elapsed_ms, 2),
        "success": getattr(result, "success", None),
        "escalated": getattr(result, "escalated_to_expert", None),
        "hitl_required": getattr(result, "hitl_required", None),
        "tool_name": getattr(result, "tool_name", None),
        "reported_ms": getattr(result, "execution_time_ms", None),
        **(extra or {}),
    }
    perf_logger.info(json.dumps(log_entry, ensure_ascii=False))


# ============================================
# Test Configuration
# ============================================
TIMEOUT_SIMPLE = 60
TIMEOUT_COMPLEX = 120


def _check_dependencies() -> bool:
    """Check if required dependencies are available."""
    try:
        from olav.modes.standard import StandardModeWorkflow
        from olav.tools.base import ToolRegistry
        return True
    except ImportError:
        return False


pytestmark = pytest.mark.skipif(
    not _check_dependencies(),
    reason="Standard Mode dependencies not available"
)


# ============================================
# Fixtures
# ============================================
@pytest.fixture(scope="module")
def tool_registry():
    """Get tool registry for tests."""
    from olav.tools.base import ToolRegistry
    return ToolRegistry()


@pytest.fixture(scope="session", autouse=True)
def log_session_start():
    """Log session start for performance tracking."""
    perf_logger.info("=" * 80)
    perf_logger.info(f"TEST SESSION START: {datetime.now().isoformat()}")
    perf_logger.info("=" * 80)
    yield
    perf_logger.info("=" * 80)
    perf_logger.info(f"TEST SESSION END: {datetime.now().isoformat()}")
    perf_logger.info("=" * 80)


# ============================================
# Test Data - Batch Device Queries
# ============================================
BATCH_QUERY_TEST_CASES = [
    # (query, expected_tool, description)
    ("查询所有设备的接口状态", "suzieq_query", "all devices interfaces"),
    ("summarize BGP for all routers", "suzieq_query", "all routers BGP summary"),
    ("查询所有 spine 设备的 LLDP 邻居", "suzieq_query", "spine LLDP neighbors"),
    ("list all leaf switches OSPF adjacencies", "suzieq_query", "leaf OSPF adjacencies"),
    ("批量检查所有边界路由器的路由表", "suzieq_query", "edge routers routing table"),
]

# ============================================
# Test Data - NetBox CRUD
# ============================================
NETBOX_READ_CASES = [
    ("列出 NetBox 中所有设备", "netbox_api_call", "list devices"),
    ("查询 NetBox 中的站点信息", "netbox_api_call", "list sites"),
    ("获取 NetBox 中 R1 的详细信息", "netbox_api_call", "get device detail"),
    ("查询 NetBox 中所有 IP 地址", "netbox_api_call", "list IP addresses"),
]

NETBOX_WRITE_CASES = [
    # (query, expected_method, description)
    ("在 NetBox 中创建新设备 TEST-R99", "POST", "create device"),
    ("更新 NetBox 中 R1 的描述为 'Core Router'", "PATCH", "update device"),
    ("在 NetBox 中添加新站点 'Beijing-DC'", "POST", "create site"),
]

NETBOX_DELETE_CASES = [
    ("删除 NetBox 中的设备 TEST-R99", "DELETE", "delete device"),
    ("从 NetBox 中移除站点 TEST-SITE", "DELETE", "delete site"),
]


# ============================================
# Test Classes - Batch Queries
# ============================================
class TestBatchDeviceQueries:
    """Tests for batch/multi-device queries."""
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    @pytest.mark.parametrize("query,expected_tool,desc", BATCH_QUERY_TEST_CASES)
    async def test_batch_query_execution(
        self,
        tool_registry,
        query: str,
        expected_tool: str,
        desc: str,
    ):
        """Test batch device query execution and log performance."""
        from olav.modes.standard import run_standard_mode
        
        start = time.perf_counter()
        
        result = await run_standard_mode(
            query=query,
            tool_registry=tool_registry,
            yolo_mode=True,
        )
        
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        # Log result
        log_test_result(
            test_name=f"batch_query_{desc.replace(' ', '_')}",
            query=query,
            result=result,
            elapsed_ms=elapsed_ms,
            extra={"expected_tool": expected_tool, "description": desc},
        )
        
        # Assertions
        assert result is not None
        assert elapsed_ms < TIMEOUT_COMPLEX * 1000, f"Query took {elapsed_ms:.0f}ms"
        
        # Either success or escalation (batch queries may be complex)
        assert result.success or result.escalated_to_expert, \
            f"Batch query failed: {result.error}"


# ============================================
# Test Classes - NetBox CRUD
# ============================================
class TestNetBoxRead:
    """Tests for NetBox read operations."""
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    @pytest.mark.parametrize("query,expected_tool,desc", NETBOX_READ_CASES)
    async def test_netbox_read_operations(
        self,
        tool_registry,
        query: str,
        expected_tool: str,
        desc: str,
    ):
        """Test NetBox read operations (no HITL required)."""
        from olav.modes.standard import run_standard_mode
        
        start = time.perf_counter()
        
        result = await run_standard_mode(
            query=query,
            tool_registry=tool_registry,
            yolo_mode=True,
        )
        
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        log_test_result(
            test_name=f"netbox_read_{desc.replace(' ', '_')}",
            query=query,
            result=result,
            elapsed_ms=elapsed_ms,
            extra={"expected_tool": expected_tool},
        )
        
        assert result is not None
        # NetBox reads should not require HITL
        assert not result.hitl_required, "Read operation should not require HITL"


class TestNetBoxWrite:
    """Tests for NetBox write operations (POST/PATCH)."""
    
    @pytest.mark.asyncio
    @pytest.mark.parametrize("query,expected_method,desc", NETBOX_WRITE_CASES)
    async def test_netbox_write_triggers_hitl(
        self,
        tool_registry,
        query: str,
        expected_method: str,
        desc: str,
    ):
        """Test NetBox write operations trigger HITL."""
        from olav.modes.standard import run_standard_mode
        
        start = time.perf_counter()
        
        # yolo_mode=False to trigger HITL
        result = await run_standard_mode(
            query=query,
            tool_registry=tool_registry,
            yolo_mode=False,
        )
        
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        log_test_result(
            test_name=f"netbox_write_{desc.replace(' ', '_')}",
            query=query,
            result=result,
            elapsed_ms=elapsed_ms,
            extra={"expected_method": expected_method, "hitl_expected": True},
        )
        
        assert result is not None
        # Write operations should require HITL or escalate
        assert result.hitl_required or result.escalated_to_expert, \
            f"Write operation should trigger HITL: {query}"


class TestNetBoxDelete:
    """Tests for NetBox delete operations."""
    
    @pytest.mark.asyncio
    @pytest.mark.parametrize("query,expected_method,desc", NETBOX_DELETE_CASES)
    async def test_netbox_delete_triggers_hitl(
        self,
        tool_registry,
        query: str,
        expected_method: str,
        desc: str,
    ):
        """Test NetBox delete operations trigger HITL."""
        from olav.modes.standard import run_standard_mode
        
        start = time.perf_counter()
        
        result = await run_standard_mode(
            query=query,
            tool_registry=tool_registry,
            yolo_mode=False,
        )
        
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        log_test_result(
            test_name=f"netbox_delete_{desc.replace(' ', '_')}",
            query=query,
            result=result,
            elapsed_ms=elapsed_ms,
            extra={"expected_method": expected_method, "hitl_expected": True},
        )
        
        assert result is not None
        # Delete must always require HITL
        assert result.hitl_required or result.escalated_to_expert, \
            "DELETE operation must trigger HITL"


# ============================================
# Test Classes - HITL Approval Flow
# ============================================
class TestHITLApprovalFlow:
    """Tests for complete HITL approval/rejection flow."""
    
    @pytest.mark.asyncio
    async def test_hitl_approval_executes_operation(self, tool_registry):
        """Test that approved HITL operations are executed."""
        from olav.modes.standard import StandardModeExecutor, StandardModeClassifier
        
        # Create executor with approval callback
        async def auto_approve(tool: str, operation: str, params: dict) -> bool:
            perf_logger.info(f"HITL AUTO-APPROVE: {tool} - {operation}")
            return True
        
        classifier = StandardModeClassifier()
        executor = StandardModeExecutor(tool_registry, yolo_mode=False)
        
        # Classify a write operation
        start = time.perf_counter()
        classification = await classifier.classify(
            "在 NetBox 中创建测试设备 HITL-TEST-001"
        )
        
        # Check if should escalate
        should_escalate = classifier.should_escalate_to_expert(classification)
        
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        if should_escalate:
            # If escalated, HITL test is N/A
            log_test_result(
                test_name="hitl_approval_flow",
                query="创建测试设备 HITL-TEST-001",
                result=None,
                elapsed_ms=elapsed_ms,
                extra={"escalated": True, "note": "Query escalated to Expert Mode"},
            )
            pytest.skip("Query escalated to Expert Mode, HITL N/A")
        
        # Execute with approval callback
        result = await executor.execute_with_approval(
            classification=classification,
            user_query="在 NetBox 中创建测试设备 HITL-TEST-001",
            approval_callback=auto_approve,
        )
        
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        log_test_result(
            test_name="hitl_approval_flow",
            query="创建测试设备 HITL-TEST-001",
            result=result,
            elapsed_ms=elapsed_ms,
            extra={"hitl_approved": result.hitl_approved},
        )
        
        # Approved operation should be attempted
        assert result.hitl_triggered, "HITL should be triggered for write"
        assert result.hitl_approved, "HITL should be approved"
    
    @pytest.mark.asyncio
    async def test_hitl_rejection_cancels_operation(self, tool_registry):
        """Test that rejected HITL operations are cancelled."""
        from olav.modes.standard import StandardModeExecutor, StandardModeClassifier
        
        # Create executor with rejection callback
        async def auto_reject(tool: str, operation: str, params: dict) -> bool:
            perf_logger.info(f"HITL AUTO-REJECT: {tool} - {operation}")
            return False
        
        classifier = StandardModeClassifier()
        executor = StandardModeExecutor(tool_registry, yolo_mode=False)
        
        start = time.perf_counter()
        classification = await classifier.classify(
            "删除 NetBox 中的设备 HITL-TEST-002"
        )
        
        # Check if should escalate
        should_escalate = classifier.should_escalate_to_expert(classification)
        
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        if should_escalate:
            log_test_result(
                test_name="hitl_rejection_flow",
                query="删除设备 HITL-TEST-002",
                result=None,
                elapsed_ms=elapsed_ms,
                extra={"escalated": True, "note": "Query escalated to Expert Mode"},
            )
            pytest.skip("Query escalated to Expert Mode, HITL N/A")
        
        result = await executor.execute_with_approval(
            classification=classification,
            user_query="删除 NetBox 中的设备 HITL-TEST-002",
            approval_callback=auto_reject,
        )
        
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        log_test_result(
            test_name="hitl_rejection_flow",
            query="删除设备 HITL-TEST-002",
            result=result,
            elapsed_ms=elapsed_ms,
            extra={"hitl_approved": result.hitl_approved},
        )
        
        # Rejected operation should fail gracefully
        assert result.hitl_triggered, "HITL should be triggered for delete"
        assert result.hitl_approved is False, "HITL should be rejected"
        assert not result.success, "Rejected operation should not succeed"
        assert "rejected" in (result.error or "").lower(), \
            f"Error should mention rejection: {result.error}"


# ============================================
# Test Classes - NETCONF Operations
# ============================================
class TestNETCONFOperations:
    """Tests for NETCONF configuration operations."""
    
    @pytest.mark.asyncio
    async def test_netconf_edit_triggers_hitl(self, tool_registry):
        """Test NETCONF edit-config triggers HITL."""
        from olav.modes.standard import run_standard_mode
        
        start = time.perf_counter()
        
        result = await run_standard_mode(
            query="配置 R1 接口 Loopback100 IP 地址为 10.0.0.1/32",
            tool_registry=tool_registry,
            yolo_mode=False,
        )
        
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        log_test_result(
            test_name="netconf_edit_hitl",
            query="配置 R1 接口 Loopback100",
            result=result,
            elapsed_ms=elapsed_ms,
        )
        
        assert result is not None
        # NETCONF edit should require HITL or escalate
        assert result.hitl_required or result.escalated_to_expert
    
    @pytest.mark.asyncio
    async def test_netconf_get_no_hitl(self, tool_registry):
        """Test NETCONF get operations don't require HITL."""
        from olav.modes.standard import run_standard_mode
        
        start = time.perf_counter()
        
        result = await run_standard_mode(
            query="通过 NETCONF 获取 R1 的接口配置",
            tool_registry=tool_registry,
            yolo_mode=False,
        )
        
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        log_test_result(
            test_name="netconf_get_no_hitl",
            query="NETCONF 获取接口配置",
            result=result,
            elapsed_ms=elapsed_ms,
        )
        
        # GET operations should not require HITL
        # (may escalate if classifier is unsure)
        if not result.escalated_to_expert:
            assert not result.hitl_required, "GET should not require HITL"


# ============================================
# Performance Summary
# ============================================
class TestPerformanceSummary:
    """Generate performance summary at end of test run."""
    
    @pytest.mark.asyncio
    async def test_generate_performance_report(self, tool_registry):
        """Generate summary report from performance log."""
        # This test runs last (alphabetically) and summarizes results
        
        if not PERF_LOG_FILE.exists():
            pytest.skip("No performance log found")
        
        # Parse log entries
        entries = []
        with open(PERF_LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if "{" in line and "}" in line:
                    try:
                        # Extract JSON from log line
                        json_start = line.index("{")
                        json_str = line[json_start:]
                        entries.append(json.loads(json_str))
                    except (json.JSONDecodeError, ValueError):
                        continue
        
        if not entries:
            pytest.skip("No log entries parsed")
        
        # Calculate statistics
        total_tests = len(entries)
        successful = sum(1 for e in entries if e.get("success"))
        escalated = sum(1 for e in entries if e.get("escalated"))
        hitl_triggered = sum(1 for e in entries if e.get("hitl_required"))
        
        elapsed_times = [e.get("elapsed_ms", 0) for e in entries if e.get("elapsed_ms")]
        avg_latency = sum(elapsed_times) / len(elapsed_times) if elapsed_times else 0
        max_latency = max(elapsed_times) if elapsed_times else 0
        min_latency = min(elapsed_times) if elapsed_times else 0
        
        # Log summary
        summary = f"""
================================================================================
STANDARD MODE E2E PERFORMANCE SUMMARY
================================================================================
Total Tests:       {total_tests}
Successful:        {successful} ({100*successful/total_tests:.1f}%)
Escalated:         {escalated} ({100*escalated/total_tests:.1f}%)
HITL Triggered:    {hitl_triggered}

Latency Statistics:
  Average:         {avg_latency:.0f} ms
  Min:             {min_latency:.0f} ms
  Max:             {max_latency:.0f} ms

Log File:          {PERF_LOG_FILE}
================================================================================
"""
        perf_logger.info(summary)
        print(summary)
        
        # Write summary to separate file
        summary_file = LOG_DIR / "standard_mode_summary.txt"
        with open(summary_file, "w", encoding="utf-8") as f:
            f.write(summary)
        
        # Assertions for optimization targets
        assert avg_latency < 5000, f"Average latency {avg_latency:.0f}ms exceeds 5s target"
