"""Unit tests for FastPathStrategy caching (Phase B.2).

Tests cover:
- Cache hit/miss scenarios
- Cache TTL expiration
- Cache key generation consistency
- Cache integration with tool execution
"""

import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import AIMessage

from olav.core.middleware import FilesystemMiddleware
from olav.strategies.fast_path import FastPathStrategy
from olav.tools.base import ToolOutput, ToolRegistry


@pytest.fixture
def mock_llm():
    """Create mock LLM for testing."""
    llm = AsyncMock()
    
    # Mock parameter extraction response
    extraction_response = AIMessage(content=json.dumps({
        "tool": "suzieq_query",
        "parameters": {"table": "bgp", "hostname": "R1"},
        "confidence": 0.95,
        "reasoning": "Simple BGP query"
    }))
    
    # Mock formatted answer response
    formatted_response = AIMessage(content=json.dumps({
        "answer": "BGP status: Established",
        "data_used": ["state", "peerASN"],
        "confidence": 0.95
    }))
    
    llm.ainvoke.side_effect = [extraction_response, formatted_response]
    return llm


@pytest.fixture
def mock_tool_registry():
    """Create mock ToolRegistry for testing."""
    registry = MagicMock(spec=ToolRegistry)
    
    # Mock tool
    mock_tool = AsyncMock()
    mock_tool.name = "suzieq_query"
    mock_tool.execute = AsyncMock(return_value=ToolOutput(
        source="suzieq",
        device="R1",
        data=[{"state": "Established", "peerASN": 65001}],
        error=None,
        metadata={"elapsed_ms": 150}
    ))
    
    registry.get_tool.return_value = mock_tool
    registry.list_tools.return_value = [mock_tool]
    
    return registry


@pytest.fixture
def test_cache_workspace(tmp_path):
    """Create temporary cache workspace for testing."""
    workspace = tmp_path / "test_cache"
    workspace.mkdir()
    return workspace


@pytest.fixture
def filesystem(test_cache_workspace):
    """Create FilesystemMiddleware for cache testing."""
    checkpointer = MemorySaver()
    return FilesystemMiddleware(
        checkpointer=checkpointer,
        workspace_root=str(test_cache_workspace),
        audit_enabled=False,
        hitl_enabled=False
    )


@pytest.fixture
def fast_path_strategy(mock_llm, mock_tool_registry, filesystem):
    """Create FastPathStrategy with caching enabled."""
    return FastPathStrategy(
        llm=mock_llm,
        tool_registry=mock_tool_registry,
        confidence_threshold=0.7,
        filesystem=filesystem,
        enable_cache=True,
        cache_ttl=300  # 5 minutes
    )


class TestCacheKeyGeneration:
    """Test cache key generation logic."""

    @pytest.mark.asyncio
    async def test_cache_key_consistency(self, fast_path_strategy):
        """Test cache keys are consistent for same input."""
        key1 = fast_path_strategy._get_cache_key("suzieq_query", {"table": "bgp", "hostname": "R1"})
        key2 = fast_path_strategy._get_cache_key("suzieq_query", {"table": "bgp", "hostname": "R1"})
        
        assert key1 == key2
        assert key1.startswith("tool_results/suzieq_query_")
        assert key1.endswith(".json")

    @pytest.mark.asyncio
    async def test_cache_key_uniqueness(self, fast_path_strategy):
        """Test cache keys are unique for different inputs."""
        key1 = fast_path_strategy._get_cache_key("suzieq_query", {"table": "bgp", "hostname": "R1"})
        key2 = fast_path_strategy._get_cache_key("suzieq_query", {"table": "bgp", "hostname": "R2"})
        key3 = fast_path_strategy._get_cache_key("netbox_api_call", {"endpoint": "/devices/"})
        
        assert key1 != key2  # Different params
        assert key1 != key3  # Different tool
        assert key2 != key3  # Both different

    @pytest.mark.asyncio
    async def test_cache_key_parameter_order_invariant(self, fast_path_strategy):
        """Test cache keys are same regardless of parameter order."""
        key1 = fast_path_strategy._get_cache_key("suzieq_query", {"table": "bgp", "hostname": "R1", "namespace": "default"})
        key2 = fast_path_strategy._get_cache_key("suzieq_query", {"hostname": "R1", "namespace": "default", "table": "bgp"})
        
        assert key1 == key2


class TestCacheMissScenario:
    """Test cache miss scenarios (no cached result available)."""

    @pytest.mark.asyncio
    async def test_cache_miss_executes_tool(self, fast_path_strategy, mock_tool_registry):
        """Test cache miss triggers tool execution."""
        tool_output = await fast_path_strategy._execute_tool(
            "suzieq_query",
            {"table": "bgp", "hostname": "R1"}
        )
        
        # Verify tool was executed
        mock_tool_registry.get_tool().execute.assert_called_once()
        assert tool_output.source == "suzieq"
        assert tool_output.device == "R1"
        assert len(tool_output.data) == 1

    @pytest.mark.asyncio
    async def test_cache_miss_writes_cache(self, fast_path_strategy, test_cache_workspace):
        """Test cache miss writes result to cache."""
        await fast_path_strategy._execute_tool(
            "suzieq_query",
            {"table": "bgp", "hostname": "R1"}
        )
        
        # Verify cache file exists
        cache_files = list(test_cache_workspace.glob("tool_results/suzieq_query_*.json"))
        assert len(cache_files) == 1
        
        # Verify cache content
        cache_content = json.loads(cache_files[0].read_text())
        assert cache_content["tool"] == "suzieq_query"
        assert cache_content["parameters"]["table"] == "bgp"
        assert cache_content["tool_output"]["source"] == "suzieq"


class TestCacheHitScenario:
    """Test cache hit scenarios (cached result available)."""

    @pytest.mark.asyncio
    async def test_cache_hit_skips_tool_execution(self, fast_path_strategy, mock_tool_registry):
        """Test cache hit skips tool execution."""
        # First call: cache miss, executes tool
        await fast_path_strategy._execute_tool("suzieq_query", {"table": "bgp", "hostname": "R1"})
        
        # Reset mock call count
        mock_tool_registry.get_tool().execute.reset_mock()
        
        # Second call: cache hit, skips tool
        tool_output = await fast_path_strategy._execute_tool("suzieq_query", {"table": "bgp", "hostname": "R1"})
        
        # Verify tool was NOT executed
        mock_tool_registry.get_tool().execute.assert_not_called()
        
        # Verify cache hit metadata
        assert tool_output.metadata["cache_hit"] is True
        assert "cache_age_seconds" in tool_output.metadata

    @pytest.mark.asyncio
    async def test_cache_hit_returns_correct_data(self, fast_path_strategy):
        """Test cache hit returns correct cached data."""
        # First call: cache miss
        original_output = await fast_path_strategy._execute_tool("suzieq_query", {"table": "bgp", "hostname": "R1"})
        
        # Second call: cache hit
        cached_output = await fast_path_strategy._execute_tool("suzieq_query", {"table": "bgp", "hostname": "R1"})
        
        # Verify data matches (excluding cache metadata)
        assert cached_output.source == original_output.source
        assert cached_output.device == original_output.device
        assert cached_output.data == original_output.data
        assert cached_output.error == original_output.error


class TestCacheTTL:
    """Test cache time-to-live expiration."""

    @pytest.mark.asyncio
    async def test_cache_expires_after_ttl(self, mock_llm, mock_tool_registry, filesystem):
        """Test cache expires after TTL seconds."""
        # Create strategy with 1-second TTL
        strategy = FastPathStrategy(
            llm=mock_llm,
            tool_registry=mock_tool_registry,
            filesystem=filesystem,
            enable_cache=True,
            cache_ttl=1  # 1 second TTL
        )
        
        # First call: cache miss
        await strategy._execute_tool("suzieq_query", {"table": "bgp", "hostname": "R1"})
        
        # Wait for cache to expire
        time.sleep(1.5)
        
        # Reset mock call count
        mock_tool_registry.get_tool().execute.reset_mock()
        
        # Second call: cache expired, executes tool again
        await strategy._execute_tool("suzieq_query", {"table": "bgp", "hostname": "R1"})
        
        # Verify tool was executed (cache expired)
        mock_tool_registry.get_tool().execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_not_expired_within_ttl(self, mock_llm, mock_tool_registry, filesystem):
        """Test cache not expired within TTL window."""
        strategy = FastPathStrategy(
            llm=mock_llm,
            tool_registry=mock_tool_registry,
            filesystem=filesystem,
            enable_cache=True,
            cache_ttl=10  # 10 seconds TTL
        )
        
        # First call: cache miss
        await strategy._execute_tool("suzieq_query", {"table": "bgp", "hostname": "R1"})
        
        # Wait briefly (within TTL)
        time.sleep(0.5)
        
        # Reset mock call count
        mock_tool_registry.get_tool().execute.reset_mock()
        
        # Second call: cache still valid
        tool_output = await strategy._execute_tool("suzieq_query", {"table": "bgp", "hostname": "R1"})
        
        # Verify tool was NOT executed (cache still valid)
        mock_tool_registry.get_tool().execute.assert_not_called()
        assert tool_output.metadata["cache_hit"] is True


class TestCacheDisabled:
    """Test behavior when caching is disabled."""

    @pytest.mark.asyncio
    async def test_cache_disabled_always_executes_tool(self, mock_llm, mock_tool_registry, filesystem):
        """Test disabled cache always executes tool."""
        strategy = FastPathStrategy(
            llm=mock_llm,
            tool_registry=mock_tool_registry,
            filesystem=filesystem,
            enable_cache=False  # Disable cache
        )
        
        # First call
        await strategy._execute_tool("suzieq_query", {"table": "bgp", "hostname": "R1"})
        
        # Second call with same params
        await strategy._execute_tool("suzieq_query", {"table": "bgp", "hostname": "R1"})
        
        # Verify tool was executed twice (no caching)
        assert mock_tool_registry.get_tool().execute.call_count == 2

    @pytest.mark.asyncio
    async def test_cache_disabled_no_cache_files(self, mock_llm, mock_tool_registry, filesystem, test_cache_workspace):
        """Test disabled cache doesn't create cache files."""
        strategy = FastPathStrategy(
            llm=mock_llm,
            tool_registry=mock_tool_registry,
            filesystem=filesystem,
            enable_cache=False
        )
        
        await strategy._execute_tool("suzieq_query", {"table": "bgp", "hostname": "R1"})
        
        # Verify no cache files created
        cache_files = list(test_cache_workspace.glob("tool_results/*.json"))
        assert len(cache_files) == 0


class TestCacheWithErrors:
    """Test cache behavior with tool execution errors."""

    @pytest.mark.asyncio
    async def test_error_result_not_cached(self, mock_llm, mock_tool_registry, filesystem, test_cache_workspace):
        """Test failed tool execution not cached."""
        # Mock tool to return error
        mock_tool_registry.get_tool().execute.return_value = ToolOutput(
            source="suzieq",
            device="R1",
            data=[],
            error="Connection timeout",
            metadata={}
        )
        
        strategy = FastPathStrategy(
            llm=mock_llm,
            tool_registry=mock_tool_registry,
            filesystem=filesystem,
            enable_cache=True
        )
        
        await strategy._execute_tool("suzieq_query", {"table": "bgp", "hostname": "R1"})
        
        # Verify no cache files created (errors not cached)
        cache_files = list(test_cache_workspace.glob("tool_results/*.json"))
        assert len(cache_files) == 0


class TestEndToEndCaching:
    """Test end-to-end caching with full FastPathStrategy execution."""

    @pytest.mark.asyncio
    async def test_full_execute_with_caching(self, mock_tool_registry, filesystem):
        """Test full execute() method with caching enabled."""
        # Create LLM mock with enough responses for 2 executions
        llm = AsyncMock()
        
        extraction_response = AIMessage(content=json.dumps({
            "tool": "suzieq_query",
            "parameters": {"table": "bgp", "hostname": "R1"},
            "confidence": 0.95,
            "reasoning": "Simple BGP query"
        }))
        
        formatted_response = AIMessage(content=json.dumps({
            "answer": "BGP status: Established",
            "data_used": ["state", "peerASN"],
            "confidence": 0.95
        }))
        
        # Set side_effect for 2 executions (4 LLM calls total: 2 extract + 2 format)
        llm.ainvoke.side_effect = [
            extraction_response,  # First execute: parameter extraction
            formatted_response,   # First execute: answer formatting
            extraction_response,  # Second execute: parameter extraction
            formatted_response,   # Second execute: answer formatting
        ]
        
        strategy = FastPathStrategy(
            llm=llm,
            tool_registry=mock_tool_registry,
            filesystem=filesystem,
            enable_cache=True,
            cache_ttl=300
        )
        
        # First execution: cache miss
        result1 = await strategy.execute("查询 R1 的 BGP 状态")
        
        assert result1["success"] is True
        assert "answer" in result1
        
        # Reset tool execution mock
        mock_tool_registry.get_tool().execute.reset_mock()
        
        # Second execution: cache hit (same parameters)
        result2 = await strategy.execute("查询 R1 的 BGP 状态")
        
        # Verify cache was used (tool not executed again)
        assert result2["success"] is True
        mock_tool_registry.get_tool().execute.assert_not_called()
