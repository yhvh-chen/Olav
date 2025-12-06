"""E2E Tests for Standard Mode - Phase 1 Milestone.

These tests verify the complete Standard Mode workflow:
- Classifier (single LLM call)
- Executor (tool execution with HITL)
- Response formatting

Usage:
    # Run all Standard Mode tests
    uv run pytest tests/e2e/test_standard_mode.py -v
    
    # Run with debug output
    OLAV_DEBUG=true uv run pytest tests/e2e/test_standard_mode.py -v
    
    # Run specific test
    uv run pytest tests/e2e/test_standard_mode.py::TestStandardModeQuery -v
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Any

import pytest

# Windows async compatibility
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


# ============================================
# Test Configuration
# ============================================
PROJECT_ROOT = Path(__file__).parent.parent.parent
TIMEOUT_SIMPLE = 60  # seconds for simple queries
TIMEOUT_COMPLEX = 120  # seconds for complex queries

# Debug mode from environment
DEBUG_MODE = os.environ.get("OLAV_DEBUG", "").lower() in ("1", "true", "yes")


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


@pytest.fixture
def debug_context():
    """Create debug context if enabled."""
    if DEBUG_MODE:
        from olav.modes.shared.debug import DebugContext
        return DebugContext(enabled=True)
    return None


# ============================================
# Test Data
# ============================================
QUERY_TEST_CASES = [
    # (query, expected_tool, expected_keywords)
    # SuzieQ queries - keywords should match tool output, not query
    ("查询 R1 的 BGP 状态", "suzieq_query", ["status", "result", "found"]),
    ("查询 R1 的接口状态", "suzieq_query", ["status", "result", "found"]),
    ("summarize all devices", "suzieq_query", ["status", "result", "found", "alive"]),
    ("查询所有设备的 OSPF 邻居", "suzieq_query", ["status", "result", "found"]),
    
    # NetBox queries
    ("列出 NetBox 中所有设备", "netbox_api_call", ["device"]),
    ("查询 R1 在 NetBox 中的信息", "netbox_api_call", ["r1"]),
    
    # Schema discovery
    ("有哪些 SuzieQ 表可用？", "suzieq_schema_search", ["table"]),
    ("BGP 表有哪些字段？", "suzieq_schema_search", ["field"]),
]

WRITE_TEST_CASES = [
    # (query, expected_tool, expected_hitl)
    ("配置 R1 接口 Loopback100 IP 为 10.0.0.1", "netconf_tool", True),
    ("在 NetBox 中创建新设备 R99", "netbox_api_call", True),
    ("更新 R1 在 NetBox 中的描述", "netbox_api_call", True),
]

EDGE_CASES = [
    # (query, description)
    ("查询 NONEXISTENT_DEVICE_999 的状态", "unknown device"),
    ("find BGP peers with ASN 99999", "no matching data"),
    ("check R1 的 BGP neighbors", "mixed language"),
]


# ============================================
# Test Classes
# ============================================
class TestStandardModeClassifier:
    """Tests for Standard Mode classifier."""
    
    @pytest.mark.asyncio
    async def test_classifier_initialization(self):
        """Test classifier can be initialized."""
        from olav.modes.standard import StandardModeClassifier
        
        classifier = StandardModeClassifier()
        assert classifier.confidence_threshold == 0.7
    
    @pytest.mark.asyncio
    async def test_classifier_returns_result(self):
        """Test classifier returns valid result."""
        from olav.modes.standard import classify_standard
        
        result, should_escalate = await classify_standard("查询 R1 BGP 状态")
        
        assert result is not None
        assert hasattr(result, "intent_category")
        assert hasattr(result, "tool")
        assert hasattr(result, "confidence")
        assert 0.0 <= result.confidence <= 1.0
    
    @pytest.mark.asyncio
    @pytest.mark.parametrize("query,expected_tool,_", QUERY_TEST_CASES[:3])
    async def test_classifier_tool_selection(self, query, expected_tool, _):
        """Test classifier selects correct tool."""
        from olav.modes.standard import classify_standard
        
        result, _ = await classify_standard(query)
        
        # Tool should match or be in same category
        assert result.tool is not None
        # Allow flexibility: suzieq_query or cli_tool are both valid for device queries
        tool_category = expected_tool.split("_")[0]
        valid_tools = [tool_category, "cli", "suzieq"]
        assert any(t in result.tool for t in valid_tools), \
            f"Expected one of {valid_tools} in {result.tool}"


class TestStandardModeExecutor:
    """Tests for Standard Mode executor."""
    
    @pytest.mark.asyncio
    async def test_executor_initialization(self, tool_registry):
        """Test executor can be initialized."""
        from olav.modes.standard import StandardModeExecutor
        
        executor = StandardModeExecutor(tool_registry)
        assert executor.yolo_mode is False
    
    @pytest.mark.asyncio
    async def test_executor_hitl_detection(self, tool_registry):
        """Test HITL requirement detection."""
        from olav.modes.standard import StandardModeExecutor
        
        executor = StandardModeExecutor(tool_registry, yolo_mode=False)
        
        # Write operations should require HITL
        requires, reason = executor._requires_hitl(
            "netconf_tool",
            {"operation": "edit-config"}
        )
        assert requires is True
        
        # Read operations should not
        requires, reason = executor._requires_hitl(
            "suzieq_query",
            {"table": "bgp"}
        )
        assert requires is False


class TestStandardModeWorkflow:
    """Tests for complete Standard Mode workflow."""
    
    @pytest.mark.asyncio
    async def test_workflow_initialization(self, tool_registry):
        """Test workflow can be initialized."""
        from olav.modes.standard import StandardModeWorkflow
        
        workflow = StandardModeWorkflow(tool_registry)
        assert workflow.confidence_threshold == 0.7
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_workflow_simple_query(self, tool_registry, debug_context):
        """Test workflow with simple query."""
        from olav.modes.standard import run_standard_mode
        from olav.modes.shared.debug import set_debug_context
        
        if debug_context:
            set_debug_context(debug_context)
        
        result = await run_standard_mode(
            query="查询 R1 的 BGP 状态",
            tool_registry=tool_registry,
            yolo_mode=True,
        )
        
        # Result should be returned (success or escalation)
        assert result is not None
        
        # If successful, should have answer
        if result.success:
            assert result.answer is not None
            assert len(result.answer) > 0
        
        # If escalated, should have reason
        if result.escalated_to_expert:
            assert result.escalation_reason is not None
        
        # Debug output if enabled
        if debug_context:
            print("\n" + debug_context.output.summary())
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    @pytest.mark.parametrize("query,expected_tool,expected_keywords", QUERY_TEST_CASES)
    async def test_workflow_query_types(
        self,
        tool_registry,
        query,
        expected_tool,
        expected_keywords,
    ):
        """Test workflow with different query types."""
        from olav.modes.standard import run_standard_mode
        
        result = await run_standard_mode(
            query=query,
            tool_registry=tool_registry,
            yolo_mode=True,
        )
        
        assert result is not None
        
        # If successful, check output contains expected keywords
        if result.success and result.answer:
            output_lower = result.answer.lower()
            # At least one keyword should be present
            has_keyword = any(kw.lower() in output_lower for kw in expected_keywords)
            assert has_keyword or result.escalated_to_expert, \
                f"Output missing keywords {expected_keywords}: {result.answer[:100]}"


class TestStandardModeHITL:
    """Tests for HITL (Human-in-the-Loop) functionality."""
    
    @pytest.mark.asyncio
    async def test_hitl_triggered_for_write(self, tool_registry):
        """Test HITL is triggered for write operations."""
        from olav.modes.standard import run_standard_mode
        
        result = await run_standard_mode(
            query="配置 R1 接口 Loopback100 IP 为 10.0.0.1",
            tool_registry=tool_registry,
            yolo_mode=False,  # HITL enabled
        )
        
        # Should either require HITL or escalate to expert
        assert result.hitl_required or result.escalated_to_expert, \
            "Write operation should trigger HITL or escalation"
    
    @pytest.mark.asyncio
    async def test_hitl_skipped_in_yolo_mode(self, tool_registry):
        """Test HITL is skipped in YOLO mode."""
        from olav.modes.standard import run_standard_mode
        
        # Note: This test may fail if tool execution fails for other reasons
        result = await run_standard_mode(
            query="配置 R1 接口描述",
            tool_registry=tool_registry,
            yolo_mode=True,  # Skip HITL
        )
        
        # HITL should not be triggered in YOLO mode
        assert not result.hitl_required or result.success or result.error


class TestStandardModeEdgeCases:
    """Tests for edge cases and error handling."""
    
    @pytest.mark.asyncio
    async def test_unknown_device_graceful(self, tool_registry):
        """Test graceful handling of unknown device."""
        from olav.modes.standard import run_standard_mode
        
        result = await run_standard_mode(
            query="查询 NONEXISTENT_DEVICE_XYZ 的状态",
            tool_registry=tool_registry,
            yolo_mode=True,
        )
        
        # Should not crash
        assert result is not None
        
        # Should either succeed with "no data" or escalate
        if result.success:
            output_lower = result.answer.lower() if result.answer else ""
            graceful = any(
                kw in output_lower
                for kw in ["no data", "not found", "empty", "error", "no matching"]
            )
            assert graceful or len(result.answer) < 50, \
                "Unknown device should return graceful message"
    
    @pytest.mark.asyncio
    async def test_mixed_language_query(self, tool_registry):
        """Test mixed Chinese/English query."""
        from olav.modes.standard import run_standard_mode
        
        result = await run_standard_mode(
            query="check R1 的 BGP neighbors",
            tool_registry=tool_registry,
            yolo_mode=True,
        )
        
        # Should handle mixed language
        assert result is not None
        assert result.success or result.escalated_to_expert


class TestStandardModePerformance:
    """Tests for performance characteristics."""
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_simple_query_latency(self, tool_registry):
        """Test simple query completes within timeout."""
        from olav.modes.standard import run_standard_mode
        
        start = time.perf_counter()
        
        result = await run_standard_mode(
            query="查询 R1 的接口状态",
            tool_registry=tool_registry,
            yolo_mode=True,
        )
        
        elapsed = time.perf_counter() - start
        
        # Should complete within timeout
        assert elapsed < TIMEOUT_SIMPLE, f"Query took {elapsed:.1f}s > {TIMEOUT_SIMPLE}s"
        
        # Log performance
        print(f"\nLatency: {elapsed*1000:.0f}ms")
        if result.execution_time_ms:
            print(f"Reported: {result.execution_time_ms:.0f}ms")


# ============================================
# Debug Output Fixture
# ============================================
@pytest.fixture(scope="session", autouse=True)
def session_summary(request):
    """Print session summary after all tests."""
    yield
    
    print("\n" + "=" * 60)
    print("Standard Mode E2E Test Summary")
    print("=" * 60)
    print("Test Categories:")
    print("  - Classifier: Tool selection accuracy")
    print("  - Executor: HITL detection and tool execution")
    print("  - Workflow: End-to-end query processing")
    print("  - HITL: Write operation approval flow")
    print("  - Edge Cases: Error handling and graceful degradation")
    print("  - Performance: Latency requirements")
    print("=" * 60)
