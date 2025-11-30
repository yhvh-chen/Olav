"""Unit tests for syslog_tool.py.

Tests the SyslogSearchTool for:
- OR query building with pipe separator
- Time range handling (start_time, end_time)
- Device IP filtering
- Severity filtering
- OpenSearch query structure
"""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from olav.tools.syslog_tool import SyslogSearchTool, syslog_search

# ============================================
# Fixtures
# ============================================


@pytest.fixture
def syslog_tool() -> SyslogSearchTool:
    """Create a SyslogSearchTool instance with mocked memory."""
    with patch("olav.tools.syslog_tool.OpenSearchMemory") as mock_memory:
        return SyslogSearchTool(memory=mock_memory.return_value)


@pytest.fixture
def mock_opensearch_results() -> list[dict[str, Any]]:
    """Sample OpenSearch results for syslog queries."""
    return [
        {
            "@timestamp": "2024-01-15T10:30:00.000Z",
            "device_ip": "192.168.1.1",
            "facility": "local0",
            "severity": "warning",
            "message": "%BGP-5-ADJCHANGE: neighbor 10.0.0.2 Down",
        },
        {
            "@timestamp": "2024-01-15T10:31:00.000Z",
            "device_ip": "192.168.1.1",
            "facility": "local0",
            "severity": "error",
            "message": "%LINK-3-UPDOWN: Interface GigabitEthernet0/1, changed state to down",
        },
        {
            "@timestamp": "2024-01-15T10:32:00.000Z",
            "device_ip": "192.168.1.2",
            "facility": "local0",
            "severity": "info",
            "message": "%SYS-5-CONFIG_I: Configured from console",
        },
    ]


# ============================================
# Query Building Tests
# ============================================


class TestQueryBuilding:
    """Tests for _build_query method."""

    def test_simple_keyword_query(self, syslog_tool: SyslogSearchTool) -> None:
        """Test simple single keyword query."""
        query = syslog_tool._build_query(keyword="BGP")

        # Query structure is directly the bool query (not wrapped in "query" key)
        assert "bool" in query
        bool_query = query["bool"]
        assert "must" in bool_query

        # Find the match query in must clauses
        must_clauses = bool_query["must"]
        assert len(must_clauses) == 1
        assert "match" in must_clauses[0]
        assert must_clauses[0]["match"]["message"] == "BGP"

    def test_or_query_with_pipe(self, syslog_tool: SyslogSearchTool) -> None:
        """Test OR query using pipe separator (BGP|OSPF|LINK)."""
        query = syslog_tool._build_query(keyword="BGP|OSPF|LINK")

        bool_query = query["bool"]
        must_clauses = bool_query["must"]

        # First must clause should be a nested bool with should
        assert len(must_clauses) == 1
        nested_bool = must_clauses[0]
        assert "bool" in nested_bool
        assert "should" in nested_bool["bool"]

        should_clauses = nested_bool["bool"]["should"]
        keywords_found = {s["match"]["message"] for s in should_clauses}
        assert keywords_found == {"BGP", "OSPF", "LINK"}
        assert nested_bool["bool"]["minimum_should_match"] == 1

    def test_time_range_filter(self, syslog_tool: SyslogSearchTool) -> None:
        """Test time range filtering with start_time and end_time."""
        query = syslog_tool._build_query(
            keyword="DOWN",
            start_time="now-1h",
            end_time="now",
        )

        bool_query = query["bool"]
        filter_clauses = bool_query.get("filter", [])

        # Find range filter for @timestamp
        range_found = False
        for clause in filter_clauses:
            if "range" in clause and "@timestamp" in clause["range"]:
                ts_range = clause["range"]["@timestamp"]
                assert ts_range.get("gte") == "now-1h"
                assert ts_range.get("lte") == "now"
                range_found = True
        assert range_found, "Expected time range filter on @timestamp"

    def test_device_ip_filter(self, syslog_tool: SyslogSearchTool) -> None:
        """Test device_ip filtering."""
        query = syslog_tool._build_query(
            keyword="ERROR",
            device_ip="192.168.1.1",
        )

        bool_query = query["bool"]
        filter_clauses = bool_query.get("filter", [])

        # Find term filter for device_ip
        ip_found = False
        for clause in filter_clauses:
            if "term" in clause and "device_ip" in clause["term"]:
                assert clause["term"]["device_ip"] == "192.168.1.1"
                ip_found = True
        assert ip_found, "Expected term filter on device_ip"

    def test_severity_filter(self, syslog_tool: SyslogSearchTool) -> None:
        """Test severity level filtering."""
        query = syslog_tool._build_query(
            keyword="CONFIG",
            severity="error",
        )

        bool_query = query["bool"]
        filter_clauses = bool_query.get("filter", [])

        # Find term filter for severity
        severity_found = False
        for clause in filter_clauses:
            if "term" in clause and "severity" in clause["term"]:
                assert clause["term"]["severity"] == "error"
                severity_found = True
        assert severity_found, "Expected term filter on severity"

    def test_combined_filters(self, syslog_tool: SyslogSearchTool) -> None:
        """Test all filters combined."""
        query = syslog_tool._build_query(
            keyword="BGP|OSPF",
            device_ip="10.0.0.1",
            severity="warning",
            start_time="2024-01-15T00:00:00Z",
            end_time="2024-01-15T23:59:59Z",
        )

        bool_query = query["bool"]

        # Verify must clause has OR query
        must_clauses = bool_query["must"]
        assert len(must_clauses) == 1
        assert "bool" in must_clauses[0]
        assert "should" in must_clauses[0]["bool"]

        # Verify filter clauses
        filter_clauses = bool_query.get("filter", [])
        # Should have: device_ip, severity, time_range
        assert len(filter_clauses) == 3, "Expected 3 filter clauses"

    def test_default_end_time_when_start_only(self, syslog_tool: SyslogSearchTool) -> None:
        """Test that end_time defaults to 'now' when only start_time is provided."""
        query = syslog_tool._build_query(
            keyword="TEST",
            start_time="now-1h",
        )

        bool_query = query["bool"]
        filter_clauses = bool_query.get("filter", [])

        for clause in filter_clauses:
            if "range" in clause and "@timestamp" in clause["range"]:
                ts_range = clause["range"]["@timestamp"]
                assert ts_range["gte"] == "now-1h"
                assert ts_range["lte"] == "now"


# ============================================
# Tool Execution Tests
# ============================================


class TestToolExecution:
    """Tests for SyslogSearchTool execution."""

    @pytest.mark.asyncio
    async def test_execute_returns_formatted_results(
        self, syslog_tool: SyslogSearchTool, mock_opensearch_results: list
    ) -> None:
        """Test that execute returns properly formatted results."""
        syslog_tool._memory.search_schema = AsyncMock(return_value=mock_opensearch_results)

        result = await syslog_tool.execute(keyword="BGP")

        assert result.error is None
        assert len(result.data) == 3

        # Verify first log entry
        first_log = result.data[0]
        assert first_log["device_ip"] == "192.168.1.1"
        assert "BGP" in first_log["message"]
        assert first_log["severity"] == "warning"

    @pytest.mark.asyncio
    async def test_execute_with_no_results(self, syslog_tool: SyslogSearchTool) -> None:
        """Test handling of empty search results."""
        syslog_tool._memory.search_schema = AsyncMock(return_value=[])

        result = await syslog_tool.execute(keyword="NONEXISTENT")

        assert result.error is None
        assert result.data == []
        assert result.metadata["result_count"] == 0

    @pytest.mark.asyncio
    async def test_execute_error_handling(self, syslog_tool: SyslogSearchTool) -> None:
        """Test error handling when OpenSearch fails."""
        syslog_tool._memory.search_schema = AsyncMock(
            side_effect=Exception("Connection refused")
        )

        result = await syslog_tool.execute(keyword="TEST")

        assert result.error is not None
        assert "Connection refused" in result.error

    @pytest.mark.asyncio
    async def test_execute_empty_keyword_error(self, syslog_tool: SyslogSearchTool) -> None:
        """Test that empty keyword returns error."""
        result = await syslog_tool.execute(keyword="")

        assert result.error is not None
        assert "empty" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_limit_clamping(
        self, syslog_tool: SyslogSearchTool, mock_opensearch_results: list
    ) -> None:
        """Test that limit is clamped between 1 and 500."""
        syslog_tool._memory.search_schema = AsyncMock(return_value=mock_opensearch_results)

        # Test over limit (should be clamped to 500)
        await syslog_tool.execute(keyword="TEST", limit=1000)
        # search_schema should be called with size=500
        call_args = syslog_tool._memory.search_schema.call_args
        assert call_args.kwargs["size"] == 500

        # Test under limit (should be clamped to 1)
        await syslog_tool.execute(keyword="TEST", limit=-5)
        call_args = syslog_tool._memory.search_schema.call_args
        assert call_args.kwargs["size"] == 1


# ============================================
# Tool Wrapper Tests
# ============================================


class TestToolWrapper:
    """Tests for the @tool decorated syslog_search function."""

    def test_wrapper_has_correct_name(self) -> None:
        """Test that the wrapper has the expected tool name."""
        assert syslog_search.name == "syslog_search"

    def test_wrapper_has_description(self) -> None:
        """Test that the wrapper has a description."""
        assert syslog_search.description is not None
        assert "syslog" in syslog_search.description.lower()


# ============================================
# Edge Case Tests
# ============================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_whitespace_in_keywords(self, syslog_tool: SyslogSearchTool) -> None:
        """Test handling of keywords with extra whitespace."""
        query = syslog_tool._build_query(keyword="  BGP  |  OSPF  ")

        bool_query = query["bool"]
        must_clauses = bool_query["must"]

        # Should have OR query
        nested_bool = must_clauses[0]
        should_clauses = nested_bool["bool"]["should"]
        keywords_found = {s["match"]["message"] for s in should_clauses}
        # Keywords should be stripped
        assert "BGP" in keywords_found
        assert "OSPF" in keywords_found
        assert "  BGP  " not in keywords_found

    def test_special_characters_in_keywords(self, syslog_tool: SyslogSearchTool) -> None:
        """Test handling of special characters in keywords."""
        # These are valid syslog message patterns
        query = syslog_tool._build_query(keyword="%BGP-5-ADJCHANGE")

        bool_query = query["bool"]
        must_clauses = bool_query["must"]

        assert must_clauses[0]["match"]["message"] == "%BGP-5-ADJCHANGE"

    def test_ipv6_device_ip(self, syslog_tool: SyslogSearchTool) -> None:
        """Test IPv6 address in device_ip filter."""
        query = syslog_tool._build_query(
            keyword="ERROR",
            device_ip="2001:db8::1",
        )

        bool_query = query["bool"]
        filter_clauses = bool_query.get("filter", [])

        ip_found = False
        for clause in filter_clauses:
            if "term" in clause and "device_ip" in clause["term"]:
                assert clause["term"]["device_ip"] == "2001:db8::1"
                ip_found = True
        assert ip_found

    def test_iso_timestamp_format(self, syslog_tool: SyslogSearchTool) -> None:
        """Test ISO 8601 timestamp in time range."""
        query = syslog_tool._build_query(
            keyword="CONFIG",
            start_time="2024-01-15T10:00:00.000Z",
            end_time="2024-01-15T12:00:00.000Z",
        )

        bool_query = query["bool"]
        filter_clauses = bool_query.get("filter", [])

        for clause in filter_clauses:
            if "range" in clause and "@timestamp" in clause["range"]:
                ts_range = clause["range"]["@timestamp"]
                assert ts_range["gte"] == "2024-01-15T10:00:00.000Z"
                assert ts_range["lte"] == "2024-01-15T12:00:00.000Z"

    def test_facility_filter(self, syslog_tool: SyslogSearchTool) -> None:
        """Test facility filtering."""
        query = syslog_tool._build_query(
            keyword="LOG",
            facility="LOCAL0",
        )

        bool_query = query["bool"]
        filter_clauses = bool_query.get("filter", [])

        facility_found = False
        for clause in filter_clauses:
            if "term" in clause and "facility" in clause["term"]:
                # Should be lowercase
                assert clause["term"]["facility"] == "local0"
                facility_found = True
        assert facility_found
