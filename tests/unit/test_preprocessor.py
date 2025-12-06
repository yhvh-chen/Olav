"""
Unit tests for QueryPreprocessor - Fast Path for Network Queries.

Tests cover:
1. Intent classification (diagnostic vs query)
2. Device name extraction
3. Fast path pattern matching
4. Integration with UnifiedClassifier
"""

import pytest

from olav.modes.shared.preprocessor import (
    DIAGNOSTIC_KEYWORDS,
    QUERY_KEYWORDS,
    QueryPreprocessor,
    preprocess_query,
)


class TestIntentClassification:
    """Test intent type classification."""

    @pytest.fixture
    def preprocessor(self):
        return QueryPreprocessor()

    @pytest.mark.parametrize(
        "query,expected_intent",
        [
            # Query intent (Standard Mode)
            ("查询 R1 的 BGP 状态", "query"),
            ("显示所有接口", "query"),
            ("列出设备", "query"),
            ("show BGP neighbors on R1", "query"),
            ("get interface status", "query"),
            ("检查路由表", "query"),
            
            # Diagnostic intent (Expert Mode)
            ("为什么 R1 和 R2 之间 BGP 断了", "diagnostic"),
            ("诊断 spine-1 连通性问题", "diagnostic"),
            ("分析网络延迟高的原因", "diagnostic"),
            ("排查 OSPF 邻居建立失败", "diagnostic"),
            ("Why is BGP down between R1 and R2", "diagnostic"),
            ("troubleshoot connectivity issue", "diagnostic"),
            
            # Network terms default to query
            ("R1 BGP", "query"),
            ("spine-1 OSPF", "query"),
        ],
    )
    def test_intent_classification(self, preprocessor, query, expected_intent):
        """Test that intent is correctly classified."""
        result = preprocessor.process(query)
        assert result.intent_type == expected_intent, f"Query: {query}"


class TestDeviceExtraction:
    """Test device name extraction."""

    @pytest.fixture
    def preprocessor(self):
        return QueryPreprocessor()

    @pytest.mark.parametrize(
        "query,expected_devices",
        [
            # Chinese patterns
            ("查询 R1 的 BGP 状态", ["R1"]),
            ("设备 spine-1 的接口", ["spine-1"]),
            ("在 leaf-2 上执行", ["leaf-2"]),
            
            # English patterns
            ("show BGP on R1", ["R1"]),
            ("device core-rtr interface status", ["core-rtr"]),
            
            # Multiple devices (future support)
            # ("R1 和 R2 之间", ["R1", "R2"]),
            
            # No device
            ("列出所有设备", []),
            ("显示所有接口状态", []),
        ],
    )
    def test_device_extraction(self, preprocessor, query, expected_devices):
        """Test that device names are correctly extracted."""
        result = preprocessor.process(query)
        assert set(result.devices) == set(expected_devices), f"Query: {query}"


class TestFastPathMatching:
    """Test fast path regex pattern matching."""

    @pytest.fixture
    def preprocessor(self):
        return QueryPreprocessor()

    @pytest.mark.parametrize(
        "query,expected_tool,expected_table",
        [
            # BGP queries
            ("查询 R1 的 BGP 状态", "suzieq_query", "bgp"),
            ("显示 R1 BGP 邻居", "suzieq_query", "bgp"),
            ("show BGP on R1", "suzieq_query", "bgp"),
            
            # Interface queries
            ("查询 R1 接口状态", "suzieq_query", "interface"),
            ("显示所有接口", "suzieq_query", "interface"),
            
            # Route queries
            ("检查 spine-1 的路由表", "suzieq_query", "routes"),
            ("查询 R1 路由", "suzieq_query", "routes"),
            
            # OSPF queries
            ("查询 R1 OSPF 邻居", "suzieq_query", "ospf"),
            
            # Device list (NetBox)
            ("列出所有设备", "netbox_api_call", None),
            ("显示设备", "netbox_api_call", None),
            
            # VLAN queries
            ("查询 R1 VLAN", "suzieq_query", "vlan"),
            
            # LLDP queries
            ("显示 R1 LLDP 邻居", "suzieq_query", "lldp"),
        ],
    )
    def test_fast_path_matching(self, preprocessor, query, expected_tool, expected_table):
        """Test that fast path patterns match correctly."""
        result = preprocessor.process(query)
        
        assert result.can_use_fast_path, f"Query should match fast path: {query}"
        assert result.fast_path_match is not None
        assert result.fast_path_match.tool == expected_tool, f"Query: {query}"
        
        if expected_table:
            assert result.fast_path_match.parameters.get("table") == expected_table

    @pytest.mark.parametrize(
        "query",
        [
            # Diagnostic queries should not use fast path
            "为什么 R1 BGP 断了",
            "诊断连通性问题",
            "分析网络故障",
            
            # Complex queries may not match
            "对比 R1 和 R2 的 BGP 配置",
            "计算所有设备的接口利用率",
        ],
    )
    def test_fast_path_not_matching(self, preprocessor, query):
        """Test that diagnostic/complex queries don't use fast path."""
        result = preprocessor.process(query)
        assert not result.can_use_fast_path, f"Query should NOT match fast path: {query}"


class TestHostnameInParameters:
    """Test that hostname is correctly added to parameters."""

    @pytest.fixture
    def preprocessor(self):
        return QueryPreprocessor()

    def test_hostname_in_bgp_query(self, preprocessor):
        """Test hostname extraction in BGP query."""
        result = preprocessor.process("查询 R1 的 BGP 状态")
        
        assert result.can_use_fast_path
        assert result.fast_path_match.parameters.get("hostname") == "R1"
        assert result.fast_path_match.parameters.get("table") == "bgp"

    def test_no_hostname_in_list_query(self, preprocessor):
        """Test no hostname in device list query."""
        result = preprocessor.process("列出所有设备")
        
        assert result.can_use_fast_path
        assert "hostname" not in result.fast_path_match.parameters


class TestPreprocessorIntegration:
    """Test preprocessor integration with classifier."""

    @pytest.mark.asyncio
    async def test_fast_path_in_classifier(self):
        """Test that classifier uses fast path when available."""
        from olav.core.unified_classifier import UnifiedClassifier
        
        classifier = UnifiedClassifier()
        
        # This should hit fast path (no LLM call)
        result = await classifier.classify("查询 R1 的 BGP 状态")
        
        # Check result
        assert result.tool == "suzieq_query"
        assert result.parameters.get("table") == "bgp"
        
        # Check that it was fast path (LLM time should be 0)
        if hasattr(result, "_fast_path"):
            assert result._fast_path is True
        if hasattr(result, "_llm_time_ms"):
            assert result._llm_time_ms == 0.0

    @pytest.mark.asyncio
    async def test_skip_fast_path_flag(self):
        """Test that skip_fast_path forces LLM classification."""
        from olav.core.unified_classifier import UnifiedClassifier
        
        classifier = UnifiedClassifier()
        
        # Force LLM path
        result = await classifier.classify(
            "查询 R1 的 BGP 状态",
            skip_fast_path=True,
        )
        
        # Should still work, but via LLM
        assert result.tool in ["suzieq_query", "suzieq_schema_search"]
        
        # LLM time should be > 0 (if attribute exists)
        if hasattr(result, "_llm_time_ms") and hasattr(result, "_fast_path"):
            # If _fast_path is not set, it went through LLM
            assert not getattr(result, "_fast_path", False)


class TestKeywordSets:
    """Test keyword set definitions."""

    def test_diagnostic_keywords_frozenset(self):
        """Ensure diagnostic keywords is immutable."""
        assert isinstance(DIAGNOSTIC_KEYWORDS, frozenset)
        assert "为什么" in DIAGNOSTIC_KEYWORDS
        assert "diagnose" in DIAGNOSTIC_KEYWORDS

    def test_query_keywords_frozenset(self):
        """Ensure query keywords is immutable."""
        assert isinstance(QUERY_KEYWORDS, frozenset)
        assert "查询" in QUERY_KEYWORDS
        assert "show" in QUERY_KEYWORDS

    def test_no_overlap(self):
        """Ensure no overlap between diagnostic and query keywords."""
        overlap = DIAGNOSTIC_KEYWORDS & QUERY_KEYWORDS
        assert len(overlap) == 0, f"Overlapping keywords: {overlap}"
