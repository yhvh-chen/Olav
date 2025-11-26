"""
Unit tests for refactored SuzieQ tool (Schema-Aware + BaseTool + SuzieqAdapter).
"""

import pandas as pd
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import time

from olav.tools.suzieq_tool import (
    SuzieQTool,
    SuzieQSchemaSearchTool,
)
from olav.tools.base import ToolOutput


class TestSuzieQTool:
    """Test SuzieQTool BaseTool implementation."""
    
    @pytest.fixture
    def mock_parquet_dir(self, tmp_path):
        """Create mock Parquet directory structure."""
        parquet_dir = tmp_path / "suzieq-parquet"
        parquet_dir.mkdir()
        
        # Create coalesced table directory
        bgp_dir = parquet_dir / "coalesced" / "bgp"
        bgp_dir.mkdir(parents=True)
        
        return parquet_dir
    
    @pytest.fixture
    def sample_bgp_df(self):
        """Create sample BGP DataFrame."""
        current_time_ms = int(time.time() * 1000)
        return pd.DataFrame([
            {
                "namespace": "default",
                "hostname": "R1",
                "peer": "10.0.0.2",
                "asn": 65001,
                "peerAsn": 65002,
                "state": "Established",
                "peerHostname": "R2",
                "active": True,
                "timestamp": current_time_ms - 3600000,  # 1 hour ago
            },
            {
                "namespace": "default",
                "hostname": "R2",
                "peer": "10.0.0.1",
                "asn": 65002,
                "peerAsn": 65001,
                "state": "Established",
                "peerHostname": "R1",
                "active": True,
                "timestamp": current_time_ms - 1800000,  # 30 min ago
            },
            {
                "namespace": "default",
                "hostname": "R1",
                "peer": "10.0.0.3",
                "asn": 65001,
                "peerAsn": 65003,
                "state": "Idle",
                "peerHostname": "R3",
                "active": False,
                "timestamp": current_time_ms - 7200000,  # 2 hours ago
            },
        ])
    
    @pytest.fixture
    def suzieq_tool(self, mock_parquet_dir):
        """Create SuzieQTool instance with mock directory."""
        return SuzieQTool(parquet_dir=mock_parquet_dir)
    
    def test_initialization(self, suzieq_tool, mock_parquet_dir):
        """Test tool initialization."""
        assert suzieq_tool.name == "suzieq_query"
        assert suzieq_tool.parquet_dir == mock_parquet_dir
        assert "SuzieQ" in suzieq_tool.description
    
    def test_initialization_missing_directory(self):
        """Test initialization with non-existent directory (should warn, not fail)."""
        tool = SuzieQTool(parquet_dir=Path("/non/existent/path"))
        assert tool.parquet_dir == Path("/non/existent/path")
    
    @pytest.mark.asyncio
    async def test_execute_unknown_table(self, suzieq_tool):
        """Test query to unknown table returns schema error."""
        result = await suzieq_tool.execute(table="nonexistent")
        
        assert isinstance(result, ToolOutput)
        assert result.source == "suzieq"
        assert result.device == "multi"
        assert "SCHEMA_ERROR" in result.data[0]["status"]
        assert "nonexistent" in result.data[0]["message"]
        assert "available_tables" in result.data[0]
        assert result.error and "not in schema" in result.error
    
    @pytest.mark.asyncio
    async def test_execute_table_no_data(self, suzieq_tool):
        """Test query to valid table with no Parquet files."""
        result = await suzieq_tool.execute(table="bgp")
        
        assert isinstance(result, ToolOutput)
        assert result.source == "suzieq"
        # When no data directory exists, returns NO_DATA or NO_PARQUET_FILES status
        if result.data:
            status = result.data[0].get("status", "")
            assert status in ("NO_DATA", "NO_PARQUET_FILES"), f"Unexpected status: {status}"
            assert "bgp" in result.data[0]["message"]
    
    @pytest.mark.asyncio
    async def test_execute_get_method(self, suzieq_tool, sample_bgp_df, mock_parquet_dir):
        """Test get method returns raw data."""
        # Write sample data to Parquet
        bgp_dir = mock_parquet_dir / "coalesced" / "bgp"
        parquet_file = bgp_dir / "data.parquet"
        sample_bgp_df.to_parquet(parquet_file)
        
        result = await suzieq_tool.execute(table="bgp", method="get")
        
        assert isinstance(result, ToolOutput)
        assert result.source == "suzieq"
        assert result.device == "multi"
        assert isinstance(result.data, list)
        # Should only have active records (deduplication filters inactive)
        assert all(record.get("active") is not False for record in result.data if "active" in record)
        assert result.metadata["table"] == "bgp"
        assert result.metadata["method"] == "get"
    
    @pytest.mark.asyncio
    async def test_execute_hostname_filter(self, suzieq_tool, sample_bgp_df, mock_parquet_dir):
        """Test hostname filtering."""
        bgp_dir = mock_parquet_dir / "coalesced" / "bgp"
        parquet_file = bgp_dir / "data.parquet"
        sample_bgp_df.to_parquet(parquet_file)
        
        result = await suzieq_tool.execute(table="bgp", hostname="R1")
        
        assert isinstance(result, ToolOutput)
        assert result.device == "R1"
        # Should only have R1 records
        for record in result.data:
            if "hostname" in record:
                assert record["hostname"] == "R1"
    
    @pytest.mark.asyncio
    async def test_execute_state_filter(self, suzieq_tool, sample_bgp_df, mock_parquet_dir):
        """Test additional field filtering."""
        bgp_dir = mock_parquet_dir / "coalesced" / "bgp"
        parquet_file = bgp_dir / "data.parquet"
        sample_bgp_df.to_parquet(parquet_file)
        
        result = await suzieq_tool.execute(table="bgp", state="Established")
        
        assert isinstance(result, ToolOutput)
        # Should only have Established peers
        for record in result.data:
            if "state" in record:
                assert record["state"] == "Established"
    
    @pytest.mark.asyncio
    async def test_execute_time_window_filter(self, suzieq_tool, sample_bgp_df, mock_parquet_dir):
        """Test max_age_hours filtering."""
        bgp_dir = mock_parquet_dir / "coalesced" / "bgp"
        parquet_file = bgp_dir / "data.parquet"
        sample_bgp_df.to_parquet(parquet_file)
        
        # Filter to last 1 hour (should exclude 2-hour-old record)
        result = await suzieq_tool.execute(table="bgp", max_age_hours=1)
        
        assert isinstance(result, ToolOutput)
        assert result.metadata["max_age_hours"] == 1
        # Should have fewer records than total
        assert len(result.data) < len(sample_bgp_df)
    
    @pytest.mark.asyncio
    async def test_execute_no_time_filter(self, suzieq_tool, sample_bgp_df, mock_parquet_dir):
        """Test max_age_hours=0 returns all data."""
        bgp_dir = mock_parquet_dir / "coalesced" / "bgp"
        parquet_file = bgp_dir / "data.parquet"
        sample_bgp_df.to_parquet(parquet_file)
        
        result = await suzieq_tool.execute(table="bgp", max_age_hours=0)
        
        assert isinstance(result, ToolOutput)
        # Should have all active records (2 out of 3 in sample data)
        assert len(result.data) >= 2
    
    @pytest.mark.asyncio
    async def test_execute_summarize_method(self, suzieq_tool, sample_bgp_df, mock_parquet_dir):
        """Test summarize method returns aggregated stats."""
        bgp_dir = mock_parquet_dir / "coalesced" / "bgp"
        parquet_file = bgp_dir / "data.parquet"
        sample_bgp_df.to_parquet(parquet_file)
        
        result = await suzieq_tool.execute(table="bgp", method="summarize")
        
        assert isinstance(result, ToolOutput)
        assert result.metadata["method"] == "summarize"
        # Summary should have aggregated fields
        assert len(result.data) > 0
        summary = result.data[0]
        assert "total_records" in summary
        assert summary["total_records"] > 0
    
    @pytest.mark.asyncio
    async def test_execute_truncation_large_dataset(self, suzieq_tool, mock_parquet_dir):
        """Test automatic truncation for datasets > 100 rows."""
        bgp_dir = mock_parquet_dir / "coalesced" / "bgp"
        parquet_file = bgp_dir / "data.parquet"
        
        # Create 150 rows
        large_df = pd.DataFrame([
            {
                "hostname": f"R{i}",
                "peer": f"10.0.0.{i}",
                "state": "Established",
                "active": True,
                "timestamp": int(time.time() * 1000),
            }
            for i in range(150)
        ])
        large_df.to_parquet(parquet_file)
        
        result = await suzieq_tool.execute(table="bgp", method="get")
        
        assert isinstance(result, ToolOutput)
        # Should be truncated to 100 rows
        assert len(result.data) <= 100
        assert result.metadata.get("truncated") is True
        assert result.metadata.get("original_count") == 100  # After head(100)
    
    @pytest.mark.asyncio
    async def test_execute_deduplication(self, suzieq_tool, mock_parquet_dir):
        """Test deduplication keeps latest record per unique key."""
        bgp_dir = mock_parquet_dir / "coalesced" / "bgp"
        parquet_file = bgp_dir / "data.parquet"
        
        current_time_ms = int(time.time() * 1000)
        duplicate_df = pd.DataFrame([
            {
                "hostname": "R1",
                "peer": "10.0.0.2",
                "afi": "ipv4",
                "safi": "unicast",
                "state": "Idle",
                "active": True,
                "timestamp": current_time_ms - 3600000,  # Older
            },
            {
                "hostname": "R1",
                "peer": "10.0.0.2",
                "afi": "ipv4",
                "safi": "unicast",
                "state": "Established",
                "active": True,
                "timestamp": current_time_ms - 1800000,  # Newer
            },
        ])
        duplicate_df.to_parquet(parquet_file)
        
        result = await suzieq_tool.execute(table="bgp", method="get")
        
        assert isinstance(result, ToolOutput)
        # Should only have 1 record (deduplicated)
        assert len(result.data) == 1
        # Should be the newer record
        assert result.data[0]["state"] == "Established"
    
    @pytest.mark.asyncio
    async def test_execute_fallback_to_non_coalesced(self, suzieq_tool, sample_bgp_df, mock_parquet_dir):
        """Test fallback to non-coalesced directory if coalesced missing."""
        # Create non-coalesced directory
        bgp_dir = mock_parquet_dir / "bgp"
        bgp_dir.mkdir(exist_ok=True)
        parquet_file = bgp_dir / "data.parquet"
        sample_bgp_df.to_parquet(parquet_file)
        
        result = await suzieq_tool.execute(table="bgp", max_age_hours=0)
        
        assert isinstance(result, ToolOutput)
        # Should have data from non-coalesced directory
        assert isinstance(result.data, list)
    
    @pytest.mark.asyncio
    async def test_execute_error_handling(self, suzieq_tool, mock_parquet_dir):
        """Test graceful error handling on read failure."""
        bgp_dir = mock_parquet_dir / "coalesced" / "bgp"
        bgp_dir.mkdir(parents=True, exist_ok=True)
        
        # Create invalid parquet file
        invalid_file = bgp_dir / "corrupt.parquet"
        invalid_file.write_text("not a parquet file")
        
        result = await suzieq_tool.execute(table="bgp")
        
        assert isinstance(result, ToolOutput)
        assert result.error is not None
        assert "failed" in result.error.lower()
    
    def test_filter_by_time_window(self, suzieq_tool, sample_bgp_df):
        """Test time window filtering logic."""
        filtered = suzieq_tool._filter_by_time_window(sample_bgp_df, max_age_hours=1)
        
        # Should exclude 2-hour-old record
        assert len(filtered) < len(sample_bgp_df)
    
    def test_deduplicate_latest_state_bgp(self, suzieq_tool):
        """Test deduplication for BGP table."""
        current_time_ms = int(time.time() * 1000)
        df = pd.DataFrame([
            {"hostname": "R1", "peer": "10.0.0.2", "afi": "ipv4", "safi": "unicast", "state": "Idle", "timestamp": current_time_ms - 3600000},
            {"hostname": "R1", "peer": "10.0.0.2", "afi": "ipv4", "safi": "unicast", "state": "Established", "timestamp": current_time_ms - 1800000},
        ])
        
        deduped = suzieq_tool._deduplicate_latest_state(df, "bgp")
        
        assert len(deduped) == 1
        assert deduped.iloc[0]["state"] == "Established"
    
    def test_deduplicate_latest_state_active_priority(self, suzieq_tool):
        """Test active=True records are prioritized."""
        current_time_ms = int(time.time() * 1000)
        df = pd.DataFrame([
            {"hostname": "R1", "peer": "10.0.0.2", "afi": "ipv4", "safi": "unicast", "active": True, "timestamp": current_time_ms},
            {"hostname": "R1", "peer": "10.0.0.2", "afi": "ipv4", "safi": "unicast", "active": False, "timestamp": current_time_ms},
        ])
        
        deduped = suzieq_tool._deduplicate_latest_state(df, "bgp")
        
        # Should only have active record
        assert all(deduped["active"] == True)
    
    def test_summarize_dataframe(self, suzieq_tool, sample_bgp_df):
        """Test summarize generates correct statistics."""
        summary_df = suzieq_tool._summarize_dataframe(sample_bgp_df)
        
        assert len(summary_df) == 1
        summary = summary_df.iloc[0]
        
        assert summary["total_records"] == len(sample_bgp_df)
        assert summary["unique_hosts"] == 2  # R1, R2
        assert "state_counts" in summary
        assert summary["state_counts"]["Established"] == 2
        assert summary["state_counts"]["Idle"] == 1


class TestSuzieQSchemaSearchTool:
    """Test SuzieQSchemaSearchTool implementation."""
    
    @pytest.fixture
    def schema_tool(self):
        """Create schema search tool instance."""
        return SuzieQSchemaSearchTool()
    
    def test_initialization(self, schema_tool):
        """Test tool initialization."""
        assert schema_tool.name == "suzieq_schema_search"
        assert "schema" in schema_tool.description.lower()
    
    @pytest.mark.asyncio
    async def test_execute_bgp_query(self, schema_tool):
        """Test schema search for BGP."""
        result = await schema_tool.execute(query="BGP information")
        
        assert isinstance(result, ToolOutput)
        assert result.source == "suzieq_schema"
        assert len(result.data) > 0
        
        # Should find BGP table
        bgp_match = next((t for t in result.data if t["table"] == "bgp"), None)
        assert bgp_match is not None
        assert "fields" in bgp_match
        assert "peer" in bgp_match["fields"]
        # Methods should include at least get and summarize (may include more like unique, aver)
        assert "get" in bgp_match["methods"]
        assert "summarize" in bgp_match["methods"]
    
    @pytest.mark.asyncio
    async def test_execute_interface_query(self, schema_tool):
        """Test schema search for interfaces."""
        result = await schema_tool.execute(query="interface status")
        
        assert isinstance(result, ToolOutput)
        
        # Should find interfaces table
        intf_match = next((t for t in result.data if t["table"] == "interfaces"), None)
        assert intf_match is not None
        assert "ifname" in intf_match["fields"]
    
    @pytest.mark.asyncio
    async def test_execute_no_matches_returns_default(self, schema_tool):
        """Test no matches returns first 5 tables."""
        result = await schema_tool.execute(query="xyzabc12345")
        
        assert isinstance(result, ToolOutput)
        # Should return up to 5 tables as default
        assert len(result.data) <= 5
        # total_tables should be >= 8 (fallback schema) or more (from OpenSearch)
        assert result.metadata["total_tables"] >= 8
    
    @pytest.mark.asyncio
    async def test_execute_multiple_keywords(self, schema_tool):
        """Test search with multiple keywords."""
        result = await schema_tool.execute(query="routing protocol ospf")
        
        assert isinstance(result, ToolOutput)
        
        # Should find OSPF and routes tables
        table_names = [t["table"] for t in result.data]
        assert "ospf" in table_names or "routes" in table_names
    
    @pytest.mark.asyncio
    async def test_execute_case_insensitive(self, schema_tool):
        """Test search is case insensitive."""
        result_lower = await schema_tool.execute(query="bgp")
        result_upper = await schema_tool.execute(query="BGP")
        
        # Should return same results
        assert len(result_lower.data) == len(result_upper.data)


class TestSuzieQToolRegistration:
    """Test tool registration with ToolRegistry."""
    
    @classmethod
    def setup_class(cls):
        """Ensure SuzieQ tools are registered before testing.
        
        Force re-registration in case previous tests cleared the registry.
        """
        from olav.tools.base import ToolRegistry
        from olav.tools.suzieq_tool import SuzieQTool, SuzieQSchemaSearchTool
        
        # Re-register tools if not present (handles state pollution)
        if not ToolRegistry.get_tool("suzieq_query"):
            ToolRegistry.register(SuzieQTool())
        if not ToolRegistry.get_tool("suzieq_schema_search"):
            ToolRegistry.register(SuzieQSchemaSearchTool())
    
    def test_tools_registered(self):
        """Test both tools are registered on import."""
        from olav.tools.base import ToolRegistry
        
        # Should have suzieq_query and suzieq_schema_search
        registered_names = [tool.name for tool in ToolRegistry.list_tools()]
        
        assert "suzieq_query" in registered_names
        assert "suzieq_schema_search" in registered_names
    
    def test_get_tool_by_name(self):
        """Test retrieving tools by name."""
        from olav.tools.base import ToolRegistry
        
        query_tool = ToolRegistry.get_tool("suzieq_query")
        assert query_tool is not None
        assert isinstance(query_tool, SuzieQTool)
        
        schema_tool = ToolRegistry.get_tool("suzieq_schema_search")
        assert schema_tool is not None
        assert isinstance(schema_tool, SuzieQSchemaSearchTool)


class TestSuzieQToolEdgeCases:
    """Test edge cases and boundary conditions."""
    
    @pytest.mark.asyncio
    async def test_empty_dataframe_handling(self, tmp_path):
        """Test handling of empty DataFrame."""
        parquet_dir = tmp_path / "suzieq-parquet"
        bgp_dir = parquet_dir / "coalesced" / "bgp"
        bgp_dir.mkdir(parents=True)
        
        # Write empty DataFrame
        empty_df = pd.DataFrame(columns=["hostname", "peer", "state"])
        parquet_file = bgp_dir / "data.parquet"
        empty_df.to_parquet(parquet_file)
        
        tool = SuzieQTool(parquet_dir=parquet_dir)
        result = await tool.execute(table="bgp")
        
        assert isinstance(result, ToolOutput)
        assert result.data == []  # SuzieqAdapter converts empty DataFrame to []
    
    @pytest.mark.asyncio
    async def test_missing_timestamp_column(self, tmp_path):
        """Test handling DataFrame without timestamp column."""
        parquet_dir = tmp_path / "suzieq-parquet"
        bgp_dir = parquet_dir / "coalesced" / "bgp"
        bgp_dir.mkdir(parents=True)
        
        # DataFrame without timestamp
        df = pd.DataFrame([
            {"hostname": "R1", "peer": "10.0.0.2", "state": "Established", "active": True}
        ])
        parquet_file = bgp_dir / "data.parquet"
        df.to_parquet(parquet_file)
        
        tool = SuzieQTool(parquet_dir=parquet_dir)
        result = await tool.execute(table="bgp", max_age_hours=24)
        
        assert isinstance(result, ToolOutput)
        # Should not crash on missing timestamp
        assert len(result.data) > 0
    
    @pytest.mark.asyncio
    async def test_namespace_filter_all(self, tmp_path):
        """Test namespace='all' returns all namespaces."""
        parquet_dir = tmp_path / "suzieq-parquet"
        bgp_dir = parquet_dir / "coalesced" / "bgp"
        bgp_dir.mkdir(parents=True)
        
        df = pd.DataFrame([
            {"hostname": "R1", "namespace": "prod", "peer": "10.0.0.2", "active": True, "timestamp": int(time.time() * 1000)},
            {"hostname": "R2", "namespace": "dev", "peer": "10.0.0.3", "active": True, "timestamp": int(time.time() * 1000)},
        ])
        parquet_file = bgp_dir / "data.parquet"
        df.to_parquet(parquet_file)
        
        tool = SuzieQTool(parquet_dir=parquet_dir)
        result = await tool.execute(table="bgp", namespace="all")
        
        assert isinstance(result, ToolOutput)
        # Should have both namespaces
        assert len(result.data) == 2
