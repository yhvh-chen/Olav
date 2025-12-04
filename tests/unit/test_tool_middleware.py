"""Unit tests for ToolMiddleware."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from olav.middleware.tool_middleware import ToolMiddleware, tool_middleware


class MockTool:
    """Mock LangChain tool for testing."""
    
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description


class TestToolMiddleware:
    """Tests for ToolMiddleware class."""
    
    def test_init(self):
        """Test middleware initialization."""
        middleware = ToolMiddleware()
        assert middleware._guide_cache == {}
        assert "suzieq_query" in middleware.TOOL_GUIDE_MAPPING
    
    def test_generate_tool_table(self):
        """Test tool table generation."""
        middleware = ToolMiddleware()
        tools = [
            MockTool("suzieq_query", "Query network state from SuzieQ."),
            MockTool("netconf_get", "Get configuration via NETCONF."),
        ]
        
        table = middleware._generate_tool_table(tools)
        
        assert "| 工具 | 用途 |" in table
        assert "`suzieq_query`" in table
        assert "`netconf_get`" in table
        assert "Query network state" in table
    
    def test_generate_tool_table_truncates_long_descriptions(self):
        """Test that long descriptions are truncated."""
        middleware = ToolMiddleware()
        long_desc = "A" * 100
        tools = [MockTool("test_tool", long_desc)]
        
        table = middleware._generate_tool_table(tools)
        
        # Should be truncated to 57 chars + "..."
        assert "..." in table
        assert long_desc not in table
    
    def test_generate_tool_table_handles_empty_description(self):
        """Test handling of tools without descriptions."""
        middleware = ToolMiddleware()
        tools = [MockTool("test_tool", "")]
        
        table = middleware._generate_tool_table(tools)
        
        assert "无描述" in table
    
    @patch("olav.middleware.tool_middleware.prompt_manager")
    def test_get_tool_guide(self, mock_prompt_manager):
        """Test capability guide loading."""
        mock_prompt_manager.load_tool_capability_guide.return_value = "Guide content"
        
        middleware = ToolMiddleware()
        guide = middleware.get_tool_guide("suzieq_query")
        
        assert guide == "Guide content"
        mock_prompt_manager.load_tool_capability_guide.assert_called_once_with("suzieq")
    
    @patch("olav.middleware.tool_middleware.prompt_manager")
    def test_get_tool_guide_caching(self, mock_prompt_manager):
        """Test that guides are cached."""
        mock_prompt_manager.load_tool_capability_guide.return_value = "Guide content"
        
        middleware = ToolMiddleware()
        
        # First call - should load
        guide1 = middleware.get_tool_guide("suzieq_query")
        # Second call - should use cache
        guide2 = middleware.get_tool_guide("suzieq_query")
        
        assert guide1 == guide2
        # Should only be called once due to caching
        assert mock_prompt_manager.load_tool_capability_guide.call_count == 1
    
    def test_get_tool_guide_unknown_tool(self):
        """Test handling of unknown tools."""
        middleware = ToolMiddleware()
        guide = middleware.get_tool_guide("unknown_tool")
        
        assert guide == ""
    
    @patch("olav.middleware.tool_middleware.prompt_manager")
    def test_enrich_prompt_basic(self, mock_prompt_manager):
        """Test basic prompt enrichment."""
        mock_prompt_manager.load_tool_capability_guide.return_value = ""
        
        middleware = ToolMiddleware()
        base_prompt = "你是网络诊断专家。"
        tools = [MockTool("suzieq_query", "Query network state.")]
        
        enriched = middleware.enrich_prompt(
            base_prompt=base_prompt,
            tools=tools,
            include_guides=False
        )
        
        assert base_prompt in enriched
        assert "## 可用工具" in enriched
        assert "`suzieq_query`" in enriched
    
    @patch("olav.middleware.tool_middleware.prompt_manager")
    def test_enrich_prompt_with_guides(self, mock_prompt_manager):
        """Test prompt enrichment with capability guides."""
        mock_prompt_manager.load_tool_capability_guide.return_value = "SuzieQ usage guide..."
        
        middleware = ToolMiddleware()
        base_prompt = "你是网络诊断专家。"
        tools = [MockTool("suzieq_query", "Query network state.")]
        
        enriched = middleware.enrich_prompt(
            base_prompt=base_prompt,
            tools=tools,
            include_guides=True
        )
        
        assert "## 工具使用指南" in enriched
        assert "SUZIEQ 工具" in enriched
        assert "SuzieQ usage guide" in enriched
    
    @patch("olav.middleware.tool_middleware.prompt_manager")
    def test_enrich_prompt_deduplicates_guides(self, mock_prompt_manager):
        """Test that guides are deduplicated by prefix."""
        mock_prompt_manager.load_tool_capability_guide.return_value = "SuzieQ guide"
        
        middleware = ToolMiddleware()
        tools = [
            MockTool("suzieq_query", "Query."),
            MockTool("suzieq_schema_search", "Search schema."),
        ]
        
        enriched = middleware.enrich_prompt(
            base_prompt="Base",
            tools=tools,
            include_guides=True
        )
        
        # Should only appear once despite two suzieq tools
        assert enriched.count("### SUZIEQ 工具") == 1
    
    def test_clear_cache(self):
        """Test cache clearing."""
        middleware = ToolMiddleware()
        middleware._guide_cache["test"] = "cached value"
        
        middleware.clear_cache()
        
        assert middleware._guide_cache == {}
    
    def test_register_tool_mapping(self):
        """Test dynamic tool mapping registration."""
        middleware = ToolMiddleware()
        
        middleware.register_tool_mapping("custom_tool", "custom")
        
        assert middleware.TOOL_GUIDE_MAPPING["custom_tool"] == "custom"
    
    def test_global_instance(self):
        """Test that global instance is available."""
        assert tool_middleware is not None
        assert isinstance(tool_middleware, ToolMiddleware)


class TestToolMiddlewareIntegration:
    """Integration tests for ToolMiddleware with real capability guides."""
    
    @pytest.mark.integration
    def test_load_real_suzieq_guide(self):
        """Test loading real SuzieQ capability guide."""
        middleware = ToolMiddleware()
        guide = middleware.get_tool_guide("suzieq_query")
        
        # Should load the actual guide file if it exists
        # This test will pass if the file exists, skip otherwise
        if not guide:
            pytest.skip("SuzieQ capability guide not found")
        
        assert len(guide) > 0
        assert "suzieq" in guide.lower() or "query" in guide.lower()

    def test_workflow_prompt_enrichment(self):
        """Test that workflow prompts can be enriched with ToolMiddleware."""
        from olav.core.prompt_manager import prompt_manager
        from olav.middleware.tool_middleware import tool_middleware
        
        # Mock tools list (same structure as workflow tools)
        mock_tools = [
            MockTool("suzieq_query", "Query SuzieQ data"),
            MockTool("suzieq_schema_search", "Search SuzieQ schema"),
        ]
        
        # Load simplified prompt (now the default)
        base_prompt = prompt_manager.load_prompt(
            "workflows/query_diagnostic", 
            "macro_analysis", 
            user_query="test query"
        )
        
        # Enrich with ToolMiddleware
        enriched = tool_middleware.enrich_prompt(
            base_prompt=base_prompt,
            tools=mock_tools,
            include_guides=True,
        )
        
        # Verify enrichment
        assert len(enriched) > len(base_prompt)
        # Check for Chinese header "可用工具" (Available Tools)
        assert "可用工具" in enriched
        assert "suzieq_query" in enriched
        assert "suzieq_schema_search" in enriched
        # Check that capability guide was included
        assert "工具使用指南" in enriched or "Capability" in enriched
