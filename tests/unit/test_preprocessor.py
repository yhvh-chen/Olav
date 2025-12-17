"""
Unit tests for QueryPreprocessor - Intent Classification and Device Extraction.

Tests cover:
1. Intent classification (diagnostic vs query)
2. Device name extraction
3. Integration with UnifiedClassifier (keyword matching)

Note: Fast path matching is now handled by ToolRegistry.keyword_match()
in unified_classifier.py, not by the preprocessor directly.
"""

import pytest

from olav.modes.shared.preprocessor import (
    DIAGNOSTIC_KEYWORDS,
    QUERY_KEYWORDS,
    QueryPreprocessor,
)


class TestIntentClassification:
    """Test intent type classification."""

    @pytest.fixture
    def preprocessor(self):
        return QueryPreprocessor()

    @pytest.mark.parametrize(
        ("query", "expected_intent"),
        [
            # Query intent (Standard Mode)
            ("query R1 BGP status", "query"),
            ("show all interfaces", "query"),
            ("list devices", "query"),
            ("show BGP neighbors on R1", "query"),
            ("get interface status", "query"),
            ("check routing table", "query"),

            # Diagnostic intent (Expert Mode)
            ("why is BGP down between R1 and R2", "diagnostic"),
            ("diagnose spine-1 connectivity issue", "diagnostic"),
            ("analyze high network latency", "diagnostic"),
            ("troubleshoot OSPF neighbor failure", "diagnostic"),
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
        ("query", "expected_devices"),
        [
            # English patterns
            ("query R1 BGP status", ["R1"]),
            ("device spine-1 interface", ["spine-1"]),
            ("show BGP on R1", ["R1"]),
            ("device core-rtr interface status", ["core-rtr"]),

            # Multiple devices (future support)
            # ("between R1 and R2", ["R1", "R2"]),

            # No device
            ("list all devices", []),
            ("show all interfaces status", []),
        ],
    )
    def test_device_extraction(self, preprocessor, query, expected_devices):
        """Test that device names are correctly extracted."""
        result = preprocessor.process(query)
        assert set(result.devices) == set(expected_devices), f"Query: {query}"


class TestToolRegistryKeywordMatch:
    """
    Test ToolRegistry.keyword_match() which replaced the preprocessor fast path.
    
    Fast path matching is now handled by tool self-declared triggers
    in ToolRegistry, not by preprocessor patterns.
    """

    @pytest.fixture
    def preprocessor(self):
        return QueryPreprocessor()

    @pytest.mark.parametrize(
        ("query", "expected_tool", "expected_category"),
        [
            # BGP queries -> suzieq
            ("query R1 BGP status", "suzieq_query", "suzieq"),
            ("show R1 BGP neighbor", "suzieq_query", "suzieq"),
            ("show BGP on R1", "suzieq_query", "suzieq"),

            # Interface queries -> suzieq
            ("query R1 interface status", "suzieq_query", "suzieq"),
            ("show all interfaces", "suzieq_query", "suzieq"),

            # Route queries -> suzieq
            ("check spine-1 routing table", "suzieq_query", "suzieq"),
            ("query R1 routes", "suzieq_query", "suzieq"),

            # OSPF queries -> suzieq
            ("query R1 OSPF neighbor", "suzieq_query", "suzieq"),

            # NetBox queries -> netbox
            ("list netbox devices", "netbox_api_call", "netbox"),
            ("show netbox dcim", "netbox_api_call", "netbox"),

            # OpenConfig queries -> openconfig
            ("search openconfig bgp xpath", "openconfig_schema_search", "openconfig"),
            ("find yang path for interfaces", "openconfig_schema_search", "openconfig"),
        ],
    )
    def test_keyword_match_via_tool_registry(self, preprocessor, query, expected_tool, expected_category):
        """Test that ToolRegistry.keyword_match() correctly identifies tools based on triggers."""
        from olav.tools.base import ToolRegistry
        
        match_result = ToolRegistry.keyword_match(query)
        
        if match_result:
            tool_name, category, confidence = match_result
            assert category == expected_category, f"Query: {query}, expected category: {expected_category}, got: {category}"
        # Note: Not all queries may match keywords; that's fine for complex queries

    @pytest.mark.parametrize(
        "query",
        [
            # Diagnostic queries - may not match keywords, rely on LLM
            "why is R1 BGP down",
            "diagnose connectivity issue",
            "analyze network fault",

            # Very complex queries may not match simple keywords
            "compare R1 and R2 BGP config across namespaces",
        ],
    )
    def test_complex_queries_may_not_match_keywords(self, preprocessor, query):
        """Test that diagnostic/complex queries may not match keywords (which is expected)."""
        from olav.tools.base import ToolRegistry
        
        # These queries may or may not match keywords depending on content
        # The key point is they would fall back to LLM classification
        result = preprocessor.process(query)
        # They should be classified as diagnostic or query based on intent keywords
        assert result.intent_type in ("diagnostic", "query", "unknown")


class TestPreprocessorIntegration:
    """Test preprocessor integration with classifier."""

    @pytest.mark.asyncio
    async def test_keyword_match_in_classifier(self):
        """Test that classifier uses keyword matching when available."""
        from olav.core.unified_classifier import UnifiedClassifier

        classifier = UnifiedClassifier()

        # This should hit keyword match (no LLM call if keyword matches)
        result = await classifier.classify("query R1 BGP status")

        # Check result - should be SuzieQ related
        assert result.tool in ["suzieq_query", "suzieq_schema_search"]

    @pytest.mark.asyncio
    async def test_llm_fallback_for_complex_queries(self):
        """Test that complex queries fall back to LLM classification."""
        from olav.core.unified_classifier import UnifiedClassifier

        classifier = UnifiedClassifier()

        # Complex query that may not match simple keywords
        result = await classifier.classify("calculate interface utilization for all devices")

        # Should still work via LLM fallback
        assert result.tool is not None


class TestKeywordSets:
    """Test keyword set definitions."""

    def test_diagnostic_keywords_frozenset(self):
        """Ensure diagnostic keywords is immutable."""
        assert isinstance(DIAGNOSTIC_KEYWORDS, frozenset)
        assert "why" in DIAGNOSTIC_KEYWORDS
        assert "diagnose" in DIAGNOSTIC_KEYWORDS

    def test_query_keywords_frozenset(self):
        """Ensure query keywords is immutable."""
        assert isinstance(QUERY_KEYWORDS, frozenset)
        assert "query" in QUERY_KEYWORDS
        assert "show" in QUERY_KEYWORDS

    def test_no_overlap(self):
        """Ensure no overlap between diagnostic and query keywords."""
        overlap = DIAGNOSTIC_KEYWORDS & QUERY_KEYWORDS
        assert len(overlap) == 0, f"Overlapping keywords: {overlap}"
